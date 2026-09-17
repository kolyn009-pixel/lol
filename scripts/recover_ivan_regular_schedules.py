from __future__ import annotations

import argparse
import os
import shutil
from datetime import datetime

import database

SCHEDULE_IDS = (9, 10, 11)
EXPECTED_USER_ID = 33
DEFAULT_START_DATE = "2026-09-17"
TARGET_END_DATE = "2026-10-31"


def _rows():
    conn = database.connect()
    try:
        q = ",".join("?" for _ in SCHEDULE_IDS)
        rows = conn.execute(
            f"SELECT * FROM regular_schedules WHERE id IN ({q}) ORDER BY id",
            SCHEDULE_IDS,
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _schedule_lesson_ids():
    conn = database.connect()
    try:
        q = ",".join("?" for _ in SCHEDULE_IDS)
        rows = conn.execute(
            f"""
            SELECT id
            FROM lessons
            WHERE regular_schedule_id IN ({q})
              AND DATE(start_time) BETWEEN ? AND ?
              AND lesson_status != 'REJECTED'
            ORDER BY start_time,id
            """,
            (*SCHEDULE_IDS, DEFAULT_START_DATE, TARGET_END_DATE),
        ).fetchall()
        return [int(r["id"]) for r in rows]
    finally:
        conn.close()


def _duplicate_lessons(user_id):
    conn = database.connect()
    try:
        rows = conn.execute(
            """
            SELECT user_id,start_time,COUNT(*) AS n,GROUP_CONCAT(id) AS lesson_ids
            FROM lessons
            WHERE user_id=?
              AND lesson_status NOT IN ('CANCELLED','REJECTED')
            GROUP BY user_id,start_time
            HAVING COUNT(*)>1
            ORDER BY start_time
            """,
            (int(user_id),),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _validate(rows):
    if [int(r["id"]) for r in rows] != list(SCHEDULE_IDS):
        raise SystemExit("RECOVERY_ABORT: schedules 9/10/11 not all present")
    for row in rows:
        if int(row["user_id"]) != EXPECTED_USER_ID:
            raise SystemExit(f"RECOVERY_ABORT: schedule {row['id']} belongs to user {row['user_id']}")
        if str(row["status"] or "").upper() != "APPROVED":
            raise SystemExit(f"RECOVERY_ABORT: schedule {row['id']} status={row['status']}, expected APPROVED")
        if int(row.get("student_approved") or 0) != 1 or int(row.get("admin_approved") or 0) != 1:
            raise SystemExit(f"RECOVERY_ABORT: schedule {row['id']} approval flags are incomplete")


def _backup(db_path):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = f"{db_path}.before-ivan-recovery-{stamp}.bak"
    shutil.copy2(db_path, backup)
    return backup


def run(apply=False):
    rows = _rows()
    _validate(rows)
    before_dupes = _duplicate_lessons(EXPECTED_USER_ID)
    if before_dupes:
        raise SystemExit(f"RECOVERY_ABORT: duplicate active lessons already exist: {before_dupes}")

    print("IVAN_RECOVERY_PREFLIGHT=OK")
    for row in rows:
        print(
            f"schedule={row['id']} weekday={row['weekday']} start={row['start_time']} "
            f"active={row['active']} start_date={row['start_date']} end_date={row['end_date']} "
            f"created_lessons_count={row.get('created_lessons_count')}"
        )

    if not apply:
        print("DRY_RUN=1")
        print(f"planned_start_date={DEFAULT_START_DATE}")
        print(f"planned_end_date={TARGET_END_DATE}")
        return

    db_path = database.current_db_name()
    if not os.path.isfile(db_path):
        raise SystemExit(f"RECOVERY_ABORT: database not found: {db_path}")
    backup = _backup(db_path)
    print(f"BACKUP={backup}")

    conn = database.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        for row in rows:
            existing_start = str(row.get("start_date") or "").strip()
            start_date = max(existing_start, DEFAULT_START_DATE) if existing_start else DEFAULT_START_DATE
            if start_date > TARGET_END_DATE:
                raise ValueError(f"schedule {row['id']} start_date after target end_date")
            cur = conn.execute(
                """
                UPDATE regular_schedules
                SET active=1,
                    start_date=?,
                    end_date=?,
                    updated_at=?
                WHERE id=? AND user_id=? AND status='APPROVED'
                """,
                (start_date, TARGET_END_DATE, database.now_iso(), int(row["id"]), EXPECTED_USER_ID),
            )
            if cur.rowcount != 1:
                raise ValueError(f"schedule {row['id']} update_not_applied")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    created = []
    for sid in SCHEDULE_IDS:
        result = database.generate_regular_lessons(int(sid))
        ids = [int(x) for x in (result.get("created") or [])]
        created.extend(ids)
        print(f"schedule={sid} generated={len(ids)} ids={ids}")

    sync_targets = _schedule_lesson_ids()
    sync = {"synced_lesson_ids": [], "failed": []}
    if sync_targets:
        from core import schedule_sync
        sync = schedule_sync.sync_lessons_blocking(sync_targets)
    print(f"SYNC_TARGETS={sync_targets}")
    print(f"SYNC={sync}")
    if sync.get("failed"):
        raise SystemExit(f"RECOVERY_FAILED: schedule sync errors: {sync['failed']}")

    after = _rows()
    for row in after:
        if int(row["active"] or 0) != 1:
            raise SystemExit(f"RECOVERY_FAILED: schedule {row['id']} is not active")
        if row["end_date"] != TARGET_END_DATE:
            raise SystemExit(f"RECOVERY_FAILED: schedule {row['id']} end_date={row['end_date']}")
        if not row["start_date"] or str(row["start_date"]) < DEFAULT_START_DATE:
            raise SystemExit(f"RECOVERY_FAILED: schedule {row['id']} start_date={row['start_date']}")

    dupes = _duplicate_lessons(EXPECTED_USER_ID)
    if dupes:
        raise SystemExit(f"RECOVERY_FAILED: duplicate active lessons found: {dupes}")

    print(f"CREATED_TOTAL={len(created)}")
    print(f"SYNC_TARGET_TOTAL={len(sync_targets)}")
    print("DUPLICATES=0")
    print("IVAN_RECOVERY=OK")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="apply recovery; default is dry-run")
    parser.add_argument("--db", help="override database path, useful for isolated test DB")
    args = parser.parse_args()
    if args.db:
        database.DB_NAME = os.path.abspath(args.db)
    run(apply=args.apply)
