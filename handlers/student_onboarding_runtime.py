from __future__ import annotations

from telegram import Update
from telegram.ext import ApplicationHandlerStop, CommandHandler, ContextTypes

from web_backend import student_onboarding, public_trial_channel


async def start_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.effective_message
    if not user or not message:
        return

    raw = (context.args[0] if getattr(context, "args", None) else "").strip()

    if raw.lower().startswith("trial_"):
        token = raw[6:].strip().upper()
        try:
            payload = public_trial_channel.confirm(
                token,
                "TELEGRAM",
                str(user.id),
                username=user.username,
                display_name=user.full_name,
            )
        except ValueError as exc:
            code = str(exc)
            if code in {"trial_link_expired", "trial_link_not_found"}:
                await message.reply_text("Ссылка пробного уже недействительна. Вернитесь на сайт Аделии и создайте новую привязку 💜")
            elif code == "wrong_channel":
                await message.reply_text("Эта ссылка создана для другого способа подключения.")
            else:
                await message.reply_text("Не удалось подключить Telegram к пробному. Вернитесь на сайт и попробуйте ещё раз.")
            raise ApplicationHandlerStop
        await message.reply_text(
            "✅ Telegram подключён к пробному занятию 💜\n\n"
            "Теперь сюда смогут прийти подтверждение времени, ссылка на занятие и важные изменения.\n\n"
            "Полное меню ученика появится только если после пробного вы решите продолжить занятия."
        )
        raise ApplicationHandlerStop

    token = ""
    if raw.lower().startswith("join_"):
        token = raw[5:].strip().upper()
    else:
        try:
            pending = student_onboarding.pending_for_external("TELEGRAM", str(user.id))
        except Exception:
            pending = None
        if pending:
            token = str(pending["token"])
        else:
            return

    try:
        payload = student_onboarding.confirm_channel(
            token,
            "TELEGRAM",
            str(user.id),
            username=user.username,
            display_name=user.full_name,
        )
    except ValueError as exc:
        code = str(exc)
        if code in {"onboarding_expired", "onboarding_not_found"}:
            await message.reply_text("Ссылка регистрации уже недействительна. Вернитесь на сайт Аделии и начните регистрацию заново 💜")
        else:
            await message.reply_text("Не удалось подтвердить Telegram. Вернитесь на сайт и попробуйте ещё раз.")
        raise ApplicationHandlerStop

    name = (payload.get("user") or {}).get("name") or payload.get("name") or user.first_name
    await message.reply_text(
        f"✅ Telegram подключён, {name}!\n\n"
        "Вернитесь на открытую страницу регистрации Аделии — она автоматически продолжится.\n\n"
        "Пока регистрация не завершена, обычное меню TutorBot открываться не будет."
    )
    raise ApplicationHandlerStop


def register(application):
    application.add_handler(CommandHandler("start", start_join), group=-184)
