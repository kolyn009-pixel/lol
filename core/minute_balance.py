"""Minute-based subscription accounting.

The legacy schema stores packages as lesson counts.  This module adds a
backwards-compatible minute layer without deleting legacy fields.  New code
uses minutes as the source of truth while old columns remain for history and
safe rollback.
"""
from __future__ import annotations

import math
from datetime import datetime

import database


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _columns(conn, table):
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _add_column(conn, table, name, definition):
    if name not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def default_duration_for_goal(study_goal: str | None) -> int:
    goal = str(study_goal or "").upper()
    # Exam/olympiad programmes default to 90 min; school support to 60 min.
    return 90 if goal in {"OGE", "EGE", "OLYMPIAD"} else 60


def ensure_schema():
    conn = database.connect()
    try:
        _add_column(conn, "student_programs", "default_duration_minutes", "INTEGER")
        _add_column(conn, "payments", "minutes_total", "INTEGER")
        _add_column(conn, "payments", "base_duration_minutes", "INTEGER")
        _add_column(conn, "payments", "hourly_rate", "INTEGER")
        _add_column(conn, "lesson_packages", "minutes_total", "INTEGER")
        _add_column(conn, "lesson_packages", "minutes_used", "INTEGER DEFAULT 0")
        _add_column(conn, "lesson_packages", "base_duration_minutes", "INTEGER")
        _add_column(conn, "lesson_packages", "hourly_rate", "INTEGER")
        _add_column(conn, "lessons", "reserved_minutes", "INTEGER DEFAULT 0")
        _add_column(conn, "lessons", "reserved_paid_minutes", "INTEGER DEFAULT 0")
        _add_column(conn, "lessons", "reserved_bonus_minutes", "INTEGER DEFAULT 0")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS lesson_minute_charges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lesson_id INTEGER NOT NULL,
                package_id INTEGER NOT NULL,
                minutes INTEGER NOT NULL,
                source_type TEXT NOT NULL,
                refunded INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                refunded_at TEXT,
                FOREIGN KEY(lesson_id) REFERENCES lessons(id) ON DELETE CASCADE,
                FOREIGN KEY(package_id) REFERENCES lesson_packages(id) ON DELETE CASCADE
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_minute_charges_lesson ON lesson_minute_charges(lesson_id, refunded)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS lesson_bonus_credits (
                lesson_id INTEGER PRIMARY KEY,
                payment_id INTEGER NOT NULL,
                package_id INTEGER NOT NULL,
                minutes INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        # Fill programme defaults only where an individual value has not been set.
        rows = conn.execute("SELECT id, study_goal FROM student_programs WHERE default_duration_minutes IS NULL OR default_duration_minutes <= 0").fetchall()
        for r in rows:
            conn.execute(
                "UPDATE student_programs SET default_duration_minutes=? WHERE id=?",
                (default_duration_for_goal(r["study_goal"]), r["id"]),
            )

        # Backfill legacy packages into minutes.  We preserve their count fields.
        pkgs = conn.execute("""
            SELECT lp.*, sp.default_duration_minutes AS program_duration
            FROM lesson_packages lp
            LEFT JOIN student_programs sp ON sp.id = lp.program_id
            WHERE lp.minutes_total IS NULL OR lp.minutes_total <= 0
        """).fetchall()
        for p in pkgs:
            duration = int(p["program_duration"] or default_duration_for_goal(p["study_goal"]))
            total = max(int(p["lessons_total"] or 0), 0) * duration
            used = min(max(int(p["lessons_used"] or 0), 0) * duration, total)
            price = int(p["price_per_lesson"] or 0)
            hourly = round(price * 60 / duration) if price > 0 and duration > 0 else 0
            conn.execute("""
                UPDATE lesson_packages
                SET minutes_total=?, minutes_used=?, base_duration_minutes=?, hourly_rate=?
                WHERE id=?
            """, (total, used, duration, hourly, p["id"]))

        # Backfill legacy payment metadata for reporting/history.
        pays = conn.execute("""
            SELECT p.*, sp.default_duration_minutes AS program_duration
            FROM payments p
            LEFT JOIN student_programs sp ON sp.id = p.program_id
            WHERE p.minutes_total IS NULL OR p.minutes_total <= 0
        """).fetchall()
        for p in pays:
            duration = int(p["program_duration"] or default_duration_for_goal(p["study_goal"]))
            count = max(int(p["lessons_count"] or 0), 0)
            total = count * duration
            price = int(p["price_per_lesson"] or 0)
            hourly = round(price * 60 / duration) if price > 0 and duration > 0 else 0
            conn.execute("""
                UPDATE payments
                SET minutes_total=?, base_duration_minutes=?, hourly_rate=?
                WHERE id=?
            """, (total, duration, hourly, p["id"]))

        conn.commit()
    finally:
        conn.close()


def get_program_duration(program_id: int) -> int:
    ensure_schema()
    conn = database.connect()
    try:
        row = conn.execute("SELECT study_goal, default_duration_minutes FROM student_programs WHERE id=?", (int(program_id),)).fetchone()
        if row is None:
            raise ValueError("Направление ученика не найдено.")
        return int(row["default_duration_minutes"] or default_duration_for_goal(row["study_goal"]))
    finally:
        conn.close()


def set_program_duration(program_id: int, minutes: int) -> int:
    ensure_schema()
    minutes = int(minutes)
    if minutes < 30 or minutes > 240 or minutes % 5:
        raise ValueError("Длительность должна быть от 30 до 240 минут и кратна 5.")
    conn = database.connect()
    try:
        cur = conn.execute(
            "UPDATE student_programs SET default_duration_minutes=?, updated_at=? WHERE id=?",
            (minutes, _now(), int(program_id)),
        )
        if cur.rowcount != 1:
            raise ValueError("Направление ученика не найдено.")
        conn.commit()
        return minutes
    finally:
        conn.close()


def effective_hourly_rate(program_id: int) -> int:
    return int(database.get_program_rate_info(int(program_id))["effective_rate"])


def price_for_minutes(hourly_rate: int, minutes: int) -> int:
    return int(round(int(hourly_rate) * int(minutes) / 60))


def package_equivalent_minutes(base_duration: int, lessons_count: int) -> int:
    return int(base_duration) * int(lessons_count)


def get_balance(user_id: int, hourly_rate: int | None = None):
    """Return paid/bonus minute balance. Bonuses are intentionally consumed first."""
    ensure_schema()
    conn = database.connect()
    try:
        sql = """
            SELECT source_type,
                   COALESCE(SUM(MAX(COALESCE(minutes_total,0)-COALESCE(minutes_used,0),0)),0) AS remaining
            FROM lesson_packages
            WHERE user_id=? AND status='ACTIVE'
              AND COALESCE(minutes_used,0) < COALESCE(minutes_total,0)
        """
        params = [int(user_id)]
        if hourly_rate is not None:
            # Bonus minutes are universal compensation; paid minutes stay within the tariff.
            sql += " AND (source_type='BONUS' OR hourly_rate=?)"
            params.append(int(hourly_rate))
        sql += " GROUP BY source_type"
        rows = conn.execute(sql, params).fetchall()
        paid = bonus = 0
        for r in rows:
            if r["source_type"] == "BONUS":
                bonus += int(r["remaining"] or 0)
            else:
                paid += int(r["remaining"] or 0)
        return {"paid": paid, "bonus": bonus, "total": paid + bonus}
    finally:
        conn.close()


def get_balance_by_rate(user_id: int):
    ensure_schema()
    conn = database.connect()
    try:
        rows = conn.execute("""
            SELECT hourly_rate, source_type,
                   COALESCE(SUM(MAX(COALESCE(minutes_total,0)-COALESCE(minutes_used,0),0)),0) AS remaining
            FROM lesson_packages
            WHERE user_id=? AND status='ACTIVE'
              AND COALESCE(minutes_used,0) < COALESCE(minutes_total,0)
            GROUP BY hourly_rate, source_type
            ORDER BY hourly_rate
        """, (int(user_id),)).fetchall()
        result = {}
        universal_bonus = 0
        for r in rows:
            remaining = int(r["remaining"] or 0)
            if r["source_type"] == "BONUS":
                universal_bonus += remaining
                continue
            rate = int(r["hourly_rate"] or 0)
            result.setdefault(rate, {"paid": 0, "bonus": 0, "total": 0})
            result[rate]["paid"] += remaining
            result[rate]["total"] += remaining
        if universal_bonus:
            result.setdefault(0, {"paid": 0, "bonus": 0, "total": 0})
            result[0]["bonus"] += universal_bonus
            result[0]["total"] += universal_bonus
        return result
    finally:
        conn.close()


def _sync_legacy_count_fields(conn, package_id: int):
    row = conn.execute("SELECT minutes_total, minutes_used, base_duration_minutes FROM lesson_packages WHERE id=?", (package_id,)).fetchone()
    if not row:
        return
    base = max(int(row["base_duration_minutes"] or 60), 1)
    total = int(row["minutes_total"] or 0)
    used = int(row["minutes_used"] or 0)
    # Legacy fields are only compatibility approximations after partial-minute use.
    conn.execute(
        "UPDATE lesson_packages SET lessons_total=?, lessons_used=? WHERE id=?",
        (math.ceil(total / base) if total else 0, min(math.floor(used / base), math.ceil(total / base) if total else 0), package_id),
    )


def reserve_minutes(user_id: int, hourly_rate: int, minutes: int, lesson_id: int):
    """Reserve/consume planned minutes for a lesson. Bonus minutes are used first.

    The charge is recorded per package so cancellation can restore exactly the same minutes.
    """
    ensure_schema()
    user_id, hourly_rate, minutes, lesson_id = int(user_id), int(hourly_rate), int(minutes), int(lesson_id)
    if minutes <= 0:
        raise ValueError("Длительность занятия должна быть больше нуля.")

    conn = database.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        already = conn.execute(
            "SELECT COALESCE(SUM(minutes),0) AS m FROM lesson_minute_charges WHERE lesson_id=? AND refunded=0",
            (lesson_id,),
        ).fetchone()["m"]
        if int(already or 0) > 0:
            conn.rollback()
            return int(already)

        rows = conn.execute("""
            SELECT * FROM lesson_packages
            WHERE user_id=? AND status='ACTIVE'
              AND COALESCE(minutes_used,0) < COALESCE(minutes_total,0)
              AND (source_type='BONUS' OR hourly_rate=?)
            ORDER BY CASE WHEN source_type='BONUS' THEN 0 ELSE 1 END, created_at, id
        """, (user_id, hourly_rate)).fetchall()
        available = sum(max(int(r["minutes_total"] or 0)-int(r["minutes_used"] or 0), 0) for r in rows)
        if available < minutes:
            conn.rollback()
            raise ValueError(f"Недостаточно минут на балансе. Доступно: {available} мин, нужно: {minutes} мин.")

        left = minutes
        paid_used = bonus_used = 0
        first_package = None
        for p in rows:
            if left <= 0:
                break
            remaining = max(int(p["minutes_total"] or 0)-int(p["minutes_used"] or 0), 0)
            take = min(remaining, left)
            if take <= 0:
                continue
            new_used = int(p["minutes_used"] or 0) + take
            status = "USED" if new_used >= int(p["minutes_total"] or 0) else "ACTIVE"
            conn.execute("UPDATE lesson_packages SET minutes_used=?, status=? WHERE id=?", (new_used, status, p["id"]))
            _sync_legacy_count_fields(conn, p["id"])
            conn.execute("""
                INSERT INTO lesson_minute_charges(lesson_id,package_id,minutes,source_type,refunded,created_at)
                VALUES(?,?,?,?,0,?)
            """, (lesson_id, p["id"], take, p["source_type"] or "PAID", _now()))
            try:
                from final_features import ledger as minute_ledger
                minute_ledger.append(user_id, "LESSON_RESERVE", program_id=p["program_id"], lesson_id=lesson_id, package_id=p["id"],
                    paid_delta=(-take if p["source_type"] != "BONUS" else 0), bonus_delta=(-take if p["source_type"] == "BONUS" else 0),
                    hourly_rate=p["hourly_rate"], reason="Резерв минут на занятие", idempotency_key=f"reserve:{lesson_id}:{p['id']}", conn=conn)
            except Exception:
                pass
            first_package = first_package or p["id"]
            if p["source_type"] == "BONUS": bonus_used += take
            else: paid_used += take
            left -= take

        conn.execute("""
            UPDATE lessons
            SET reserved_minutes=?, reserved_paid_minutes=?, reserved_bonus_minutes=?,
                package_id=?, charged=1, payment_status='RESERVED_BALANCE', updated_at=?
            WHERE id=?
        """, (minutes, paid_used, bonus_used, first_package, _now(), lesson_id))
        conn.commit()
        return minutes
    finally:
        conn.close()


def refund_lesson_minutes(lesson_id: int) -> bool:
    ensure_schema()
    lesson_id = int(lesson_id)
    conn = database.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        charges = conn.execute(
            "SELECT * FROM lesson_minute_charges WHERE lesson_id=? AND refunded=0 ORDER BY id",
            (lesson_id,),
        ).fetchall()
        if not charges:
            conn.rollback()
            return False
        for c in charges:
            p = conn.execute("SELECT * FROM lesson_packages WHERE id=?", (c["package_id"],)).fetchone()
            if p:
                new_used = max(int(p["minutes_used"] or 0) - int(c["minutes"] or 0), 0)
                conn.execute("UPDATE lesson_packages SET minutes_used=?, status='ACTIVE' WHERE id=?", (new_used, p["id"]))
                _sync_legacy_count_fields(conn, p["id"])
            conn.execute("UPDATE lesson_minute_charges SET refunded=1, refunded_at=? WHERE id=?", (_now(), c["id"]))
            try:
                from final_features import ledger as minute_ledger
                minute_ledger.append(p["user_id"] if p else 0, "LESSON_REFUND", program_id=(p["program_id"] if p else None), lesson_id=lesson_id, package_id=c["package_id"],
                    paid_delta=(int(c["minutes"] or 0) if c["source_type"] != "BONUS" else 0), bonus_delta=(int(c["minutes"] or 0) if c["source_type"] == "BONUS" else 0),
                    hourly_rate=(p["hourly_rate"] if p else None), reason="Возврат минут после отмены", idempotency_key=f"refund:{lesson_id}:{c['id']}", conn=conn)
            except Exception:
                pass
        conn.execute("""
            UPDATE lessons SET reserved_minutes=0,reserved_paid_minutes=0,reserved_bonus_minutes=0,
                charged=0,payment_status='REFUNDED',package_id=NULL,updated_at=? WHERE id=?
        """, (_now(), lesson_id))
        conn.commit()
        return True
    finally:
        conn.close()


def add_bonus_minutes(user_id: int, program_id: int | None, minutes: int, reason="UNDERWORKED_TIME_CREDIT", lesson_id: int | None = None):
    """Credit bonus minutes once.

    When lesson_id is supplied, lesson_bonus_credits makes the operation
    idempotent across retries and process crashes.
    """
    ensure_schema()
    minutes = int(minutes)
    if minutes <= 0:
        return None
    if program_id:
        program = database.get_student_program(int(program_id))
    else:
        program = None
    study_goal = program["study_goal"] if program else "BONUS"
    subject = program["subject"] if program else "GENERAL"
    base = get_program_duration(program_id) if program_id else 60
    conn = database.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if lesson_id is not None:
            existing = conn.execute(
                "SELECT package_id FROM lesson_bonus_credits WHERE lesson_id=?",
                (int(lesson_id),),
            ).fetchone()
            if existing:
                conn.rollback()
                return int(existing["package_id"])
        cur = conn.execute("""
            INSERT INTO payments(user_id,study_goal,subject,payment_type,lessons_count,price_per_lesson,
                subtotal,discount_percent,package_discount_amount,promo_discount_amount,total_amount,status,
                created_at,confirmed_at,program_id,minutes_total,base_duration_minutes,hourly_rate)
            VALUES(?,?,?,'BONUS',0,0,0,0,0,0,0,'PAID',?,?,?,?,?,0)
        """, (int(user_id), study_goal, subject, _now(), _now(), int(program_id) if program_id else None, minutes, base))
        payment_id = cur.lastrowid
        cur = conn.execute("""
            INSERT INTO lesson_packages(payment_id,user_id,study_goal,subject,lessons_total,lessons_used,
                price_per_lesson,discount_percent,amount_paid,status,source_type,bonus_reason,created_at,program_id,
                minutes_total,minutes_used,base_duration_minutes,hourly_rate)
            VALUES(?,?,?,?,0,0,0,0,0,'ACTIVE','BONUS',?,?,?,?,0,?,0)
        """, (payment_id,int(user_id),study_goal,subject,reason,_now(),int(program_id) if program_id else None,minutes,base))
        package_id = cur.lastrowid
        if lesson_id is not None:
            conn.execute(
                "INSERT INTO lesson_bonus_credits(lesson_id,payment_id,package_id,minutes,created_at) VALUES(?,?,?,?,?)",
                (int(lesson_id), int(payment_id), int(package_id), minutes, _now()),
            )
        try:
            from final_features import ledger as minute_ledger
            minute_ledger.append(int(user_id), "BONUS_CREDIT", program_id=(int(program_id) if program_id else None),
                lesson_id=(int(lesson_id) if lesson_id is not None else None), payment_id=payment_id, package_id=package_id,
                bonus_delta=minutes, hourly_rate=0, reason=reason,
                idempotency_key=(f"underwork:lesson:{int(lesson_id)}" if lesson_id is not None else f"bonus:package:{package_id}"), conn=conn)
        except Exception:
            pass
        conn.commit()
        return package_id
    finally:
        conn.close()


def credit_confirmed_payment(payment_id: int, package_id: int | None = None):
    """Populate minute metadata after a payment is confirmed.

    Safe to call repeatedly.  Package rows created by legacy confirmation are upgraded in place.
    """
    ensure_schema()
    conn = database.connect()
    try:
        p = conn.execute("SELECT * FROM payments WHERE id=?", (int(payment_id),)).fetchone()
        if not p:
            return
        base = int(p["base_duration_minutes"] or default_duration_for_goal(p["study_goal"]))
        total = int(p["minutes_total"] or (int(p["lessons_count"] or 0) * base))
        hourly = int(p["hourly_rate"] or (round(int(p["price_per_lesson"] or 0)*60/base) if base else 0))
        conn.execute("UPDATE payments SET minutes_total=?,base_duration_minutes=?,hourly_rate=? WHERE id=?", (total,base,hourly,p["id"]))
        if package_id is None:
            rows = conn.execute("SELECT id FROM lesson_packages WHERE payment_id=?", (p["id"],)).fetchall()
        else:
            rows = [{"id": int(package_id)}]
        for r in rows:
            pkg = conn.execute("SELECT * FROM lesson_packages WHERE id=?", (r["id"],)).fetchone()
            if not pkg:
                continue
            # A direct one-lesson payment is already consumed; packages are not.
            legacy_used = int(pkg["lessons_used"] or 0)
            used = min(total, legacy_used * base)
            conn.execute("""
                UPDATE lesson_packages
                SET minutes_total=?,minutes_used=?,base_duration_minutes=?,hourly_rate=?,
                    program_id=COALESCE(program_id, ?)
                WHERE id=?
            """, (total,used,base,hourly,p["program_id"],pkg["id"]))
            try:
                from final_features import ledger as minute_ledger
                opening=max(total-used,0)
                minute_ledger.append(p["user_id"], "PAYMENT_CREDIT", program_id=p["program_id"], payment_id=p["id"], package_id=pkg["id"],
                    paid_delta=opening, money=int(p["total_amount"] or 0), hourly_rate=hourly, reason="Подтверждённая оплата", idempotency_key=f"payment:{p['id']}:package:{pkg['id']}", conn=conn)
            except Exception:
                pass
        conn.commit()
    finally:
        conn.close()


def prepaid_value_rubles() -> int:
    """Current monetary value of paid, unused minutes (bonus excluded)."""
    ensure_schema()
    conn = database.connect()
    try:
        rows = conn.execute("""
            SELECT hourly_rate, COALESCE(minutes_total,0)-COALESCE(minutes_used,0) AS mins
            FROM lesson_packages
            WHERE status='ACTIVE' AND source_type!='BONUS'
              AND COALESCE(minutes_total,0)>COALESCE(minutes_used,0)
        """).fetchall()
        return int(round(sum(int(r["hourly_rate"] or 0) * int(r["mins"] or 0) / 60 for r in rows)))
    finally:
        conn.close()


def admin_adjust_minutes(user_id: int, program_id: int, delta_minutes: int, reason="ADMIN_ADJUSTMENT"):
    """Manual minute correction. Positive minutes are non-cash bonus/adjustment minutes.
    Negative corrections consume bonus first, then paid minutes at the programme tariff.
    """
    delta_minutes = int(delta_minutes)
    if delta_minutes == 0:
        return None
    if delta_minutes > 0:
        return add_bonus_minutes(user_id, program_id, delta_minutes, reason=reason)

    ensure_schema()
    rate = effective_hourly_rate(program_id)
    need = abs(delta_minutes)
    conn = database.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute("""
            SELECT * FROM lesson_packages
            WHERE user_id=? AND status='ACTIVE'
              AND COALESCE(minutes_used,0)<COALESCE(minutes_total,0)
              AND (source_type='BONUS' OR hourly_rate=?)
            ORDER BY CASE WHEN source_type='BONUS' THEN 0 ELSE 1 END, created_at, id
        """, (int(user_id), int(rate))).fetchall()
        available = sum(max(int(r["minutes_total"] or 0)-int(r["minutes_used"] or 0),0) for r in rows)
        if available < need:
            conn.rollback()
            raise ValueError(f"Недостаточно минут. Доступно: {available} мин.")
        left=need
        touched=[]
        for p in rows:
            if left<=0: break
            remaining=max(int(p["minutes_total"] or 0)-int(p["minutes_used"] or 0),0)
            take=min(remaining,left)
            if take<=0: continue
            new_used=int(p["minutes_used"] or 0)+take
            status='USED' if new_used>=int(p["minutes_total"] or 0) else 'ACTIVE'
            conn.execute("UPDATE lesson_packages SET minutes_used=?,status=? WHERE id=?",(new_used,status,p["id"]))
            _sync_legacy_count_fields(conn,p["id"])
            try:
                from final_features import ledger as minute_ledger
                minute_ledger.append(int(user_id), "ADMIN_ADJUST", program_id=int(program_id), package_id=p["id"],
                    paid_delta=(-take if p["source_type"] != "BONUS" else 0), bonus_delta=(-take if p["source_type"] == "BONUS" else 0), hourly_rate=p["hourly_rate"], reason=reason, conn=conn)
            except Exception:
                pass
            touched.append((p["id"],take))
            left-=take
        conn.commit()
        return touched
    finally:
        conn.close()
