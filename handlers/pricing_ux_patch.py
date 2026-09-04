from __future__ import annotations

import database
from telegram.ext import CallbackQueryHandler
from handlers import review_v2, runtime_patch_v2


def _grade_for_user(user_id):
    c = database.connect()
    try:
        row = c.execute("SELECT grade FROM users WHERE id=?", (int(user_id),)).fetchone()
        return int(row["grade"]) if row and row["grade"] is not None else None
    finally:
        c.close()


def _effective_price_for_lesson_row(row):
    try:
        return int(review_v2._lesson_price(row))
    except Exception:
        return int(row["price"] or 0)


def _patch_review_grade():
    if getattr(review_v2, "_adelia_grade_patch", False):
        return

    original_payment_cases = review_v2._payment_cases
    original_no_next_cases = review_v2._no_next_cases
    original_case_text = review_v2._case_text

    def payment_cases():
        cases = original_payment_cases()
        for case in cases:
            case["grade"] = _grade_for_user(case["user_id"])
        return cases

    def no_next_cases():
        cases = original_no_next_cases()
        for case in cases:
            case["grade"] = _grade_for_user(case["user_id"])
        return cases

    def case_text(case, index, total):
        text = original_case_text(case, index, total)
        grade = case.get("grade")
        if grade is not None:
            text = text.replace(
                f"👤 {case['name']}",
                f"👤 {case['name']} • {grade} класс",
                1,
            )
        return text

    review_v2._payment_cases = payment_cases
    review_v2._no_next_cases = no_next_cases
    review_v2._case_text = case_text
    review_v2._adelia_grade_patch = True


async def _primary_review_entry(update, context):
    """Route every daily-review entry to the sequential review_v2 flow.

    Older ux_final review screens used the ux_review_start callback and showed
    grouped summaries. The production workflow is now review_v2: exactly one
    actionable problem at a time, with Done / Defer-to-date / Next controls.
    """
    q = update.callback_query
    if not q:
        return

    await q.answer()
    context.user_data["mh_review_started_at"] = review_v2._now().isoformat(timespec="seconds")
    context.user_data["mh_review_entry"] = str(q.data or "ux_review_start")
    await review_v2._show(q, context, 0)


def _install_primary_review_route(application):
    if application is None:
        return
    if getattr(application, "_adelia_primary_review_route", False):
        return

    # Negative group makes this route win before the legacy ux_final handler.
    application.add_handler(
        CallbackQueryHandler(
            _primary_review_entry,
            pattern=r"^ux_review_start(?:\|.*)?$",
        ),
        group=-100,
    )
    application._adelia_primary_review_route = True


def debts(limit=40):
    """One debt card per student, only for the nearest unpaid confirmed lesson."""
    c = database.connect()
    try:
        rows = c.execute("""
            SELECT
                u.id,
                u.name,
                u.grade,
                l.id AS lesson_id,
                l.user_id,
                l.program_id,
                l.study_goal,
                l.subject,
                l.duration_minutes,
                l.price,
                l.start_time AS since
            FROM users u
            JOIN lessons l
              ON l.id = (
                  SELECT l2.id
                  FROM lessons l2
                  WHERE l2.user_id=u.id
                    AND l2.lesson_status='CONFIRMED'
                    AND l2.cancelled_at IS NULL
                    AND l2.finished_at IS NULL
                    AND datetime(l2.start_time)>=datetime('now')
                  ORDER BY datetime(l2.start_time)
                  LIMIT 1
              )
            WHERE u.active=1
              AND l.payment_status='AWAITING_PAYMENT'
            ORDER BY datetime(l.start_time)
            LIMIT ?
        """, (int(limit),)).fetchall()

        result = []
        for row in rows:
            result.append({
                "id": int(row["id"]),
                "name": row["name"],
                "grade": int(row["grade"]) if row["grade"] is not None else None,
                "cnt": 1,
                "amount": _effective_price_for_lesson_row(row),
                "since": row["since"],
            })
        return result
    finally:
        c.close()


def weekly_payment_snapshot():
    """Current actionable payment cases using effective individual rates."""
    cases = [c for c in review_v2.review_cases(include_done=True) if c["kind"] == "PAYMENT_NEXT"]
    return {
        "count": len(cases),
        "amount": sum(int(c.get("price") or 0) for c in cases),
    }


def install(application=None):
    _patch_review_grade()
    _install_primary_review_route(application)

    try:
        from handlers import musthave_admin
        musthave_admin._debts = debts
    except Exception as exc:
        print("ADELIA PRICING UX DEBTS PATCH ERROR:", repr(exc))

    # Keep runtime patch's public hook coherent for modules that import it later.
    runtime_patch_v2.debts = debts
