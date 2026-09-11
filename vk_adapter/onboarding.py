from __future__ import annotations

import re

from web_backend import student_onboarding

TOKEN_RE = re.compile(r"\bJOIN-[A-Z0-9]{10}\b", re.I)


def try_handle(app_module, peer_id, vk_user_id, raw_text):
    """Consume a website JOIN code before the ordinary VK student router."""
    raw = str(raw_text or "").strip()
    match = TOKEN_RE.search(raw.upper())
    if not match:
        return False
    token = match.group(0).upper()
    try:
        profile = app_module._profile(vk_user_id)
        payload = student_onboarding.confirm_channel(
            token,
            "VK",
            str(vk_user_id),
            profile.get("username"),
            profile.get("display_name"),
        )
        name = (payload.get("user") or {}).get("name") or payload.get("name") or ""
        app_module.send(
            peer_id,
            "✅ ВКонтакте подключён к регистрации Аделии" + (f", {name}" if name else "") + ".\n\n"
            "Вернитесь на открытую страницу регистрации — она автоматически продолжится.\n\n"
            "Полное меню ученика откроется после завершения регистрации.",
            False,
        )
    except ValueError as exc:
        code = str(exc)
        text = "Код регистрации не найден или уже истёк." if code in {"onboarding_not_found", "onboarding_expired"} else "Не удалось подтвердить ВКонтакте. Проверьте код на сайте Аделии."
        app_module.send(peer_id, "❌ " + text, False)
    return True
