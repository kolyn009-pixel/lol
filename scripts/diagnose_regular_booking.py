#!/usr/bin/env python3
"""Read-only production diagnostic for recurring lesson availability.

Opens SQLite using mode=ro. It never imports database.py and never writes,
migrates, checkpoints WAL, or changes settings.
"""
from __future__ import annotations

import argparse
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

ODD_WEEK_ANCHOR = date(2026, 8, 31)
STEP = 30
DAY_NAMES = ["MON","TUE","WED","THU","FRI","SAT","SUN"]


def minutes(value):
    h, m = [int(x) for x in str(value)[:5].split(":")]
    return h * 60 + m


def clock(value):
    h, m = divmod(value, 60)
    return f"{h:02d}:{m:02d}"


def week_kind(day):
    weeks = (day - ODD_WEEK_ANCHOR).days // 7
    return "ODD" if weeks % 2 == 0 else "EVEN"


def setting(conn, key, default=None):
    row = conn.execute("SELECT value FROM bot_settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row and row["value"] is not None else default


def truthy_setting(conn, key, default="1"):
    return str(setting(conn, key, default)).lower() not in {"0","false","off","no"}


def working_rows(conn, weekday, kind):
    rows = conn.execute(
        """SELECT weekday,start_time,end_time,COALESCE(week_type,'ALL') week_type
           FROM working_hours
           WHERE active=1 AND weekday=? AND COALESCE(week_type,'ALL')=?
           ORDER BY start_time""",
        (weekday, kind),
    ).fetchall()
    return rows


def effective_rows(conn, day):
    mode = str(setting(conn, "teacher_week_mode", "SAME") or "SAME").upper()
    weekday = day.weekday()
    if mode == "SAME":
        return working_rows(conn, weekday, "ALL")
    kind = week_kind(day)
    enabled_key = "teacher_odd_week_enabled" if kind == "ODD" else "teacher_even_week_enabled"
    if not truthy_setting(conn, enabled_key, "1"):
        return []
    if truthy_setting(conn, f"teacher_week_day_off_{kind}_{weekday}", "0"):
        return []
    specific = working_rows(conn, weekday, kind)
    return specific or working_rows(conn, weekday, "ALL")


def recurring_busy(conn, weekday, start_min, end_min):
    rows = conn.execute(
        """SELECT id,user_id,start_time,duration_minutes,status,COALESCE(active,0) active
           FROM regular_schedules
           WHERE weekday=?
             AND (
               status='PENDING'
               OR (COALESCE(active,0)=1 AND status='APPROVED')
             )
           ORDER BY start_time,id""",
        (weekday,),
    ).fetchall()
    conflicts = []
    for row in rows:
        rs = minutes(row["start_time"])
        re = rs + int(row["duration_minutes"] or 60)
        if start_min < re and rs < end_min:
            conflicts.append(row)
    return conflicts


def slots_for_day(conn, day, duration):
    result = []
    for row in effective_rows(conn, day):
        cur = minutes(row["start_time"])
        end = minutes(row["end_time"])
        while cur + duration <= end:
            conflicts = recurring_busy(conn, day.weekday(), cur, cur + duration)
            if not conflicts:
                result.append(clock(cur))
            cur += STEP
    return sorted(set(result))


def next_weekday(start, weekday):
    day = start
    while day.weekday() != weekday:
        day += timedelta(days=1)
    return day


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("db", type=Path)
    ap.add_argument("--duration", type=int, default=90)
    args = ap.parse_args()

    db = args.db.resolve()
    if not db.is_file():
        raise SystemExit(f"DB_NOT_FOUND={db}")
    uri = f"file:{db}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        print("===== REGULAR BOOKING READ-ONLY DIAGNOSTIC =====")
        print(f"DB={db}")
        print(f"DURATION={args.duration}")
        print(f"MODE={str(setting(conn,'teacher_week_mode','SAME') or 'SAME').upper()}")
        print(f"BOT_TIMEZONE={setting(conn,'bot_timezone','Europe/Samara')}")
        print(f"ODD_ENABLED={truthy_setting(conn,'teacher_odd_week_enabled','1')}")
        print(f"EVEN_ENABLED={truthy_setting(conn,'teacher_even_week_enabled','1')}")
        print()

        print("===== ACTIVE/PENDING REGULAR SCHEDULES =====")
        rows = conn.execute(
            """SELECT id,user_id,weekday,start_time,duration_minutes,status,
                      COALESCE(active,0) active,start_date,end_date
               FROM regular_schedules
               WHERE status='PENDING'
                  OR (COALESCE(active,0)=1 AND status='APPROVED')
               ORDER BY weekday,start_time,id"""
        ).fetchall()
        if not rows:
            print("NONE")
        for r in rows:
            print(
                f"id={r['id']} user={r['user_id']} day={DAY_NAMES[int(r['weekday'])]} "
                f"time={r['start_time']} duration={r['duration_minutes']} "
                f"status={r['status']} active={r['active']} "
                f"period={r['start_date'] or '-'}..{r['end_date'] or '-'}"
            )
        print()

        today = date.today()
        mode = str(setting(conn, "teacher_week_mode", "SAME") or "SAME").upper()
        print("===== 90-MINUTE WEEKLY AVAILABILITY =====")
        total = 0
        for weekday in range(7):
            anchor = next_weekday(today, weekday)
            samples = []
            day = anchor
            for _ in range(5):
                samples.append((day, week_kind(day), slots_for_day(conn, day, args.duration)))
                day += timedelta(days=7)

            if mode == "SAME":
                offered = samples[0][2]
            else:
                odd = next((s for d,k,s in samples if k == "ODD"), [])
                even = next((s for d,k,s in samples if k == "EVEN"), [])
                offered = sorted(set(odd) & set(even))

            print(f"{DAY_NAMES[weekday]} offered={','.join(offered) if offered else '-'}")
            for d, kind, slots in samples[:2]:
                intervals = ",".join(
                    f"{r['start_time']}-{r['end_time']}"
                    for r in effective_rows(conn, d)
                ) or "-"
                print(
                    f"  {d.isoformat()} {kind} working={intervals} "
                    f"free={','.join(slots) if slots else '-'}"
                )
            total += len(offered)

        print()
        print(f"TOTAL_OFFERED_SLOTS={total}")
        if total == 0:
            print("RESULT=NO_RECURRING_SLOTS")
        else:
            print("RESULT=RECURRING_SLOTS_AVAILABLE")
        print("READ_ONLY=YES")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
