from __future__ import annotations

import database


def _vk_peer(user_id: int):
    c = database.connect()
    try:
        row = c.execute(
            """
            SELECT external_id
            FROM channel_identities
            WHERE user_id=? AND channel='VK' AND enabled=1
            LIMIT 1
            """,
            (int(user_id),),
        ).fetchone()
        return int(row["external_id"]) if row else None
    finally:
        c.close()


def _lesson_started(lesson_id: int) -> bool:
    c = database.connect()
    try:
        row = c.execute(
            "SELECT started_at, lesson_status FROM lessons WHERE id=?",
            (int(lesson_id),),
        ).fetchone()
        if not row:
            return False
        return bool(row["started_at"]) or str(row["lesson_status"] or "").upper() == "IN_PROGRESS"
    finally:
        c.close()


def _message(user, lesson, meeting_url: str) -> str:
    board_url = str(user["board_url"] or "").strip()
    subject = {"PHYSICS": "Физика", "CHEMISTRY": "Химия"}.get(
        str(lesson["subject"] or "").upper(),
        str(lesson["subject"] or "Занятие"),
    )
    parts = [
        "🔗 ССЫЛКИ НА ЗАНЯТИЕ",
        "",
        f"📖 {subject}",
        "",
        "🎥 Подключиться к занятию:",
        str(meeting_url).strip(),
    ]
    if board_url:
        parts += ["", "📝 Доска занятия:", board_url]
    parts += ["", "Можно подключаться прямо из VK 💜"]
    return "\n".join(parts)


def send_to_vk(user_id: int, lesson_id: int, meeting_url: str):
    peer = _vk_peer(user_id)
    if not peer:
        return False
    user = database.get_user(int(user_id))
    lesson = database.get_lesson(int(lesson_id))
    if not user or not lesson:
        return False

    from . import app as vk_app
    vk_app.send(peer, _message(user, lesson, meeting_url), linked=True)
    return True


def install():
    """Mirror the exact manually supplied lesson URL to VK after Telegram succeeds.

    The existing Telegram admin flow remains authoritative: teacher presses
    'send lesson link', enters the fresh Telemost URL, TutorBot sends it to
    Telegram and starts the lesson. Only after that succeeds do we mirror the
    same URL plus the student's permanent board_url to a linked VK account.
    """
    import admin

    if getattr(admin, "_vk_lesson_link_bridge_installed", False):
        return

    original = admin.send_link_and_start_lesson

    async def wrapped(context, lesson_id, value, force=False):
        result = await original(context, lesson_id, value, force=force)

        try:
            if _lesson_started(int(lesson_id)):
                lesson = database.get_lesson(int(lesson_id))
                if lesson:
                    send_to_vk(int(lesson["user_id"]), int(lesson_id), str(value))
        except Exception as exc:
            # VK must never break the existing Telegram lesson-start flow.
            print("VK LESSON LINK MIRROR ERROR:", repr(exc))

        return result

    admin.send_link_and_start_lesson = wrapped
    admin._vk_lesson_link_bridge_installed = True
