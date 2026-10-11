"""Telegram download controls backed by persisted homework attachments."""
from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import PurePath

from telegram import InlineKeyboardButton, InputFile

import homework_attachments
import homework_pdf_runtime as PDF


def _name(row):
    raw = PDF.attachment_filename(row).replace("\\", "/")
    return PurePath(raw).name or "homework"


def buttons(homework_id, attachments):
    return [
        [InlineKeyboardButton(
            "📎 Получить " + _name(row)[:38],
            callback_data=f"hw6_file|{int(homework_id)}|{int(row['id'])}",
        )]
        for row in attachments
    ]


def primary_media(row):
    """Prefer our server copy to an external Telegram file ID."""
    stored = row["content_blob"] if "content_blob" in row.keys() else None
    if stored:
        return InputFile(BytesIO(bytes(stored)), filename=_name(row))
    return PDF.telegram_file_id(row)


async def send(bot, chat_id, homework_id, attachment_id):
    row = PDF.attachment(homework_id, attachment_id)
    if not row:
        raise FileNotFoundError("Файл не найден.")
    try:
        content = await asyncio.to_thread(
            homework_attachments._ensure_content_blob, dict(row)
        )
    except (OSError, ValueError, RuntimeError):
        # Legacy assignments may only have a Telegram reference.
        fid = PDF.telegram_file_id(row)
        if not fid:
            raise FileNotFoundError("Файл недоступен. Попросите преподавателя прикрепить его заново.")
        document = fid
    else:
        document = InputFile(BytesIO(content), filename=_name(row))
    return await bot.send_document(
        int(chat_id), document=document, caption="📎 Файл домашнего задания"
    )
