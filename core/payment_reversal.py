"""Atomic correction of a mistaken manual confirmation, never a bank refund."""
from __future__ import annotations

import json
from datetime import datetime, timezone
import database
from core import minute_balance


def _table(c, name):
    return bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


def _provider_paid(c, p):
    if any(str(p.get(k) or "").upper() in {"YOOKASSA", "ROBOKASSA"} for k in ("provider", "payment_provider", "payment_type")):
        return True
    return _table(c, "robokassa_invoices") and bool(c.execute(
        "SELECT 1 FROM robokassa_invoices WHERE payment_id=? AND state='SETTLED'", (p["id"],)).fetchone())


def _state(c, payment_id):
    row = c.execute("SELECT * FROM payments WHERE id=?", (int(payment_id),)).fetchone()
    if not row:
        raise ValueError("payment_not_found")
    p = dict(row)
    if p["status"] == "REVERSED":
        return p, [], [], []
    if p["status"] != "PAID":
        raise ValueError("payment_not_paid")
    if int(p.get("total_amount") or 0) <= 0 or p.get("payment_type") == "BONUS":
        raise ValueError("bonus_payment_not_reversible")
    if _provider_paid(c, p):
        raise ValueError("provider_payment_requires_refund")
    packages = [dict(r) for r in c.execute("SELECT * FROM lesson_packages WHERE payment_id=?", (p["id"],))]
    if not packages:
        raise ValueError("payment_package_missing")
    ids = [x["id"] for x in packages]
    marks = ",".join("?" for _ in ids)
    charges = [dict(r) for r in c.execute(
        f"SELECT * FROM lesson_minute_charges WHERE package_id IN ({marks}) AND refunded=0", ids)]
    lessons = {r["id"]: dict(r) for r in c.execute(
        f"SELECT * FROM lessons WHERE payment_id=? OR package_id IN ({marks})", [p["id"], *ids])}
    for charge in charges:
        r = c.execute("SELECT * FROM lessons WHERE id=?", (charge["lesson_id"],)).fetchone()
        if r:
            lessons[r["id"]] = dict(r)
    if any(int(x["user_id"]) != int(p["user_id"]) for x in [*packages, *lessons.values()]):
        raise ValueError("payment_links_inconsistent")
    return p, packages, charges, list(lessons.values())


def preview(payment_id):
    minute_balance.ensure_schema()
    c = database.connect()
    try:
        p, packages, charges, lessons = _state(c, payment_id)
        user = c.execute("SELECT name FROM users WHERE id=?", (p["user_id"],)).fetchone()
        return {"payment_id": p["id"], "user_id": p["user_id"], "name": user["name"] if user else "",
                "amount": int(p["total_amount"] or 0), "status": p["status"],
                "lesson_ids": [x["id"] for x in lessons], "lessons_count": len(lessons),
                "remaining_minutes": sum(max(0, int(x["minutes_total"] or 0)-int(x["minutes_used"] or 0)) for x in packages)}
    finally:
        c.close()


def _ledger(c, p, package, operation, delta, now, actor_id, reason, key, money=0, lesson_id=None):
    if not _table(c, "minute_ledger"):
        return
    bonus = package.get("source_type") == "BONUS"
    c.execute("""INSERT OR IGNORE INTO minute_ledger
        (user_id,program_id,lesson_id,payment_id,package_id,operation,paid_minutes_delta,
         bonus_minutes_delta,money_rubles,hourly_rate,reason,actor_id,idempotency_key,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (p["user_id"], package.get("program_id"), lesson_id, p["id"], package["id"], operation,
         0 if bonus else delta, delta if bonus else 0, money, package.get("hourly_rate"),
         reason, actor_id, key, now))


def reverse(payment_id, *, actor_id, source, reason="Ошибочное подтверждение оплаты"):
    if not actor_id:
        raise PermissionError("actor_required")
    reason = str(reason or "").strip()[:500]
    if not reason:
        raise ValueError("reason_required")
    minute_balance.ensure_schema()
    c = database.connect()
    try:
        c.execute("BEGIN IMMEDIATE")
        c.execute("""CREATE TABLE IF NOT EXISTS payment_reversals(
            payment_id INTEGER PRIMARY KEY, actor_id INTEGER NOT NULL, source TEXT NOT NULL,
            reason TEXT NOT NULL, snapshot TEXT NOT NULL, result TEXT NOT NULL, reversed_at TEXT NOT NULL)""")
        p, packages, _, lessons = _state(c, payment_id)
        if p["status"] == "REVERSED":
            audit = c.execute("SELECT result FROM payment_reversals WHERE payment_id=?", (p["id"],)).fetchone()
            if not audit:
                raise ValueError("reversal_audit_missing")
            result = json.loads(audit["result"])
            result["already_reversed"] = True
            c.rollback()
            return result
        now = database.now_iso()
        # Historical manual lesson confirmations may predate the minute
        # ledger. Only counter money that was actually recorded there.
        ledger_money = 0
        if _table(c, "minute_ledger"):
            ledger_money = max(0, int(c.execute(
                "SELECT COALESCE(SUM(money_rubles),0) FROM minute_ledger WHERE payment_id=?",
                (p["id"],)).fetchone()[0]))
        snapshot = {"payment": p, "packages": packages, "lessons": lessons, "charges": []}
        snapshot["receipts"] = [dict(x) for x in c.execute("SELECT * FROM receipts WHERE payment_id=?", (p["id"],))]
        if _table(c, "promo_code_usages"):
            snapshot["promo_usages"] = [dict(x) for x in c.execute("SELECT * FROM promo_code_usages WHERE payment_id=?", (p["id"],))]
        for lesson in lessons:
            # Release the whole mixed reservation. Real paid/bonus packages are
            # restored; the cancelled package is disabled below in this same lock.
            charges = c.execute("SELECT * FROM lesson_minute_charges WHERE lesson_id=? AND refunded=0", (lesson["id"],)).fetchall()
            snapshot["charges"].extend(dict(x) for x in charges)
            for charge in charges:
                package_row = c.execute("SELECT * FROM lesson_packages WHERE id=?", (charge["package_id"],)).fetchone()
                if not package_row:
                    raise ValueError("charge_package_missing")
                package = dict(package_row)
                if int(package["user_id"]) != int(p["user_id"]):
                    raise ValueError("payment_links_inconsistent")
                if package["status"] not in {"REVERSED", "CANCELLED"}:
                    used = max(0, int(package["minutes_used"] or 0)-int(charge["minutes"]))
                    c.execute("UPDATE lesson_packages SET minutes_used=?,status=CASE WHEN status IN ('ACTIVE','USED') THEN 'ACTIVE' ELSE status END WHERE id=?", (used, package["id"]))
                    minute_balance._sync_legacy_count_fields(c, package["id"])
                    _ledger(c, p, package, "PAYMENT_REVERSAL_RELEASE", int(charge["minutes"]), now,
                            actor_id, reason, f"payment-reverse:{p['id']}:charge:{charge['id']}", lesson_id=lesson["id"])
                c.execute("UPDATE lesson_minute_charges SET refunded=1,refunded_at=? WHERE id=?", (now, charge["id"]))
            # Keep lesson times and lifecycle, including completed lessons.
            # No new auto-cancellation deadline is introduced by a correction.
            c.execute("""UPDATE lessons SET payment_status='AWAITING_PAYMENT',
                payment_id=NULL,package_id=NULL,charged=0,reserved_minutes=0,
                reserved_paid_minutes=0,reserved_bonus_minutes=0,payment_deadline=NULL,updated_at=?
                WHERE id=?""", (now, lesson["id"]))
        for index, package in enumerate(packages):
            row = c.execute("SELECT minutes_total,minutes_used FROM lesson_packages WHERE id=?", (package["id"],)).fetchone()
            remaining = max(0, int(row["minutes_total"] or 0)-int(row["minutes_used"] or 0))
            _ledger(c, p, package, "PAYMENT_REVERSAL", -remaining, now, actor_id, reason,
                    f"payment-reverse:{p['id']}:package:{package['id']}",
                    money=-ledger_money if index == 0 else 0)
            c.execute("UPDATE lesson_packages SET status='REVERSED' WHERE id=?", (package["id"],))
        c.execute("UPDATE payments SET status='REVERSED' WHERE id=?", (p["id"],))
        c.execute("UPDATE receipts SET status='REJECTED',reviewed_at=? WHERE payment_id=? AND status IN ('WAITING','APPROVED')", (now, p["id"]))
        if _table(c, "promo_code_usages"):
            usages = c.execute("SELECT promo_id,COUNT(*) n FROM promo_code_usages WHERE payment_id=? GROUP BY promo_id", (p["id"],)).fetchall()
            for usage in usages:
                c.execute("UPDATE promo_codes SET uses_count=MAX(0,uses_count-?),updated_at=? WHERE id=?", (usage["n"], now, usage["promo_id"]))
            c.execute("DELETE FROM promo_code_usages WHERE payment_id=?", (p["id"],))
        result = {"status": "ok", "payment_id": p["id"], "user_id": p["user_id"],
                  "amount": int(p["total_amount"]), "lesson_ids": [x["id"] for x in lessons],
                  "reversed_at": datetime.now(timezone.utc).isoformat(), "already_reversed": False}
        c.execute("INSERT INTO payment_reversals VALUES(?,?,?,?,?,?,?)",
                  (p["id"], int(actor_id), str(source)[:30], reason,
                   json.dumps(snapshot, ensure_ascii=False), json.dumps(result, ensure_ascii=False), result["reversed_at"]))
        c.commit()
        return result
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def notify(result):
    if result.get("already_reversed"):
        return
    try:
        from web_backend import push_events
        push_events.student_and_parents(
            result["user_id"], "Статус оплаты исправлен",
            f"Подтверждение оплаты {result['amount']} ₽ отменено преподавателем как ошибочное. Проверьте счёт в кабинете.",
            "/app/", "/app/parent/", f"payment-reversed-{result['payment_id']}",
            {"type": "payment_reversed", "payment_id": result["payment_id"]})
    except Exception as exc:
        print("PAYMENT REVERSAL NOTIFY:", type(exc).__name__, flush=True)
