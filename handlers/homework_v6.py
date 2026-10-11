from __future__ import annotations

import asyncio
from io import BytesIO

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
    InputMediaPhoto,
)

from telegram.ext import (
    ApplicationHandlerStop,
    CallbackQueryHandler,
)

import database
import homework_pdf_runtime as PDF
from . import homework_file_delivery as FILES

from formula_library import (
    FORMULA_LIBRARY,
)


def _hw(hid):
    return database.get_homework(
        int(hid)
    )


def _user(tid):
    return (
        database
        .get_user_by_telegram_id(
            int(tid)
        )
    )


def _owns(tid, hid):
    hw = _hw(
        hid
    )

    user = _user(
        tid
    )

    return bool(
        hw
        and user
        and int(hw["user_id"])
        == int(user["id"])
    )


def _done(hw):
    return (
        str(
            hw["status"]
            or ""
        ).upper()
        in {
            "DONE",
            "APPROVED",
            "REVIEWED",
            "COMPLETED",
        }
    )


def _links(hid):
    c = database.connect()

    try:
        return list(
            c.execute(
                """
                SELECT *
                FROM homework_formula_links
                WHERE homework_id=?
                ORDER BY id
                """,
                (int(hid),),
            ).fetchall()
        )

    finally:
        c.close()


def _caption(
    hw,
    page=None,
    pages=None,
    extra=None,
):
    lines = [
        "📝 ДОМАШНЕЕ ЗАДАНИЕ",
        "",
        str(
            hw["description"]
            or "Задание во вложении"
        ),
    ]

    if hw["deadline"]:
        lines += [
            "",
            f"⏰ Срок: {hw['deadline']}",
        ]

    if (
        page is not None
        and pages is not None
    ):
        lines += [
            "",
            f"📄 Страница {page} из {pages}",
        ]

    if extra:
        lines += [
            "",
            "━━━━━━━━━━━━",
            str(extra),
        ]

    if _done(hw):
        lines += [
            "",
            "✅ ДЗ выполнено",
        ]

    return "\n".join(
        lines
    )[:1000]


def _markup(
    hid,
    aid,
    page,
    pages,
    done=False,
):
    nav = []

    if page > 1:
        nav.append(
            InlineKeyboardButton(
                "◀️",
                callback_data=(
                    f"hw6_page|"
                    f"{hid}|{aid}|{page - 1}"
                ),
            )
        )
    else:
        nav.append(
            InlineKeyboardButton(
                "·",
                callback_data="hw6_nop",
            )
        )

    nav.append(
        InlineKeyboardButton(
            f"{page} / {pages}",
            callback_data="hw6_nop",
        )
    )

    if page < pages:
        nav.append(
            InlineKeyboardButton(
                "▶️",
                callback_data=(
                    f"hw6_page|"
                    f"{hid}|{aid}|{page + 1}"
                ),
            )
        )
    else:
        nav.append(
            InlineKeyboardButton(
                "·",
                callback_data="hw6_nop",
            )
        )

    return InlineKeyboardMarkup([
        nav,

        [
            InlineKeyboardButton(
                "📄 Оригинал PDF",
                callback_data=(
                    f"hw6_original|"
                    f"{hid}|{aid}"
                ),
            )
        ],

        [
            InlineKeyboardButton(
                "📚 Формулы",
                callback_data=(
                    f"hw6_formula|"
                    f"{hid}|{aid}|{page}"
                ),
            ),
            InlineKeyboardButton(
                (
                    "✅ ДЗ выполнено"
                    if done
                    else "✅ Выполнено"
                ),
                callback_data=(
                    f"hw6_home|"
                    f"{hid}|{aid}|{page}"
                    if done
                    else (
                        f"hw6_done|"
                        f"{hid}|{aid}|{page}"
                    )
                ),
            ),
        ],

        *FILES.buttons(hid, PDF.attachments(hid)),

        [
            InlineKeyboardButton(
                "⬅️ К списку ДЗ",
                callback_data="homework",
            )
        ],
    ])


async def _payload(
    hid,
    aid,
    page,
):
    cached = PDF.cached_page(
        aid,
        page,
    )

    if (
        cached
        and cached[
            "telegram_file_id"
        ]
    ):
        return {
            "file_id": cached[
                "telegram_file_id"
            ],
            "bytes": None,
            "page": int(
                cached["page_number"]
            ),
            "pages": int(
                cached["page_count"]
            ),
        }

    rendered = (
        await asyncio.to_thread(
            PDF.render_page,
            hid,
            aid,
            page,
        )
    )

    return {
        "file_id": None,
        **rendered,
    }


async def send_homework(
    bot,
    chat_id,
    hid,
):
    hw = _hw(
        hid
    )

    if not hw:
        return None

    attachments = PDF.attachments(
        hid
    )

    if not attachments:
        return await bot.send_message(
            int(chat_id),
            _caption(hw),
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "📚 Формулы",
                        callback_data=(
                            f"hw6_formula_text|{hid}"
                        ),
                    ),
                    InlineKeyboardButton(
                        "✅ Выполнено",
                        callback_data=(
                            f"hw6_done_text|{hid}"
                        ),
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "⬅️ К ДЗ",
                        callback_data="homework",
                    )
                ],
            ]),
        )

    primary = attachments[0]

    if not PDF.is_pdf(
        primary
    ):
        fid = FILES.primary_media(primary)

        if not fid:
            return await bot.send_message(
                int(chat_id),
                _caption(
                    hw,
                    extra=(
                        "⚠️ Старое вложение "
                        "нужно прикрепить заново."
                    ),
                ),
            )

        kind = str(
            (
                primary["file_type"]
                if "file_type"
                in primary.keys()
                else None
            )
            or (
                primary["kind"]
                if "kind"
                in primary.keys()
                else None
            )
            or "document"
        ).lower()

        markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📚 Формулы",
                    callback_data=(
                        f"hw6_formula_text|{hid}"
                    ),
                ),
                InlineKeyboardButton(
                    "✅ Выполнено",
                    callback_data=(
                        f"hw6_done_text|{hid}"
                    ),
                ),
            ],
            *FILES.buttons(hid, attachments),

            [
                InlineKeyboardButton(
                    "⬅️ К ДЗ",
                    callback_data="homework",
                )
            ],
        ])

        if kind == "photo":
            return await bot.send_photo(
                int(chat_id),
                photo=fid,
                caption=_caption(hw),
                reply_markup=markup,
            )

        return await bot.send_document(
            int(chat_id),
            document=fid,
            caption=_caption(hw),
            reply_markup=markup,
        )

    aid = int(
        primary["id"]
    )

    payload = await _payload(
        hid,
        aid,
        1,
    )

    if payload["file_id"]:
        photo = payload[
            "file_id"
        ]
    else:
        photo = InputFile(
            BytesIO(
                payload["bytes"]
            ),
            filename=(
                f"homework_{hid}_"
                "page_1.jpg"
            ),
        )

    msg = await bot.send_photo(
        int(chat_id),
        photo=photo,
        caption=_caption(
            hw,
            payload["page"],
            payload["pages"],
        ),
        reply_markup=_markup(
            hid,
            aid,
            payload["page"],
            payload["pages"],
            done=_done(hw),
        ),
    )

    try:
        if msg.photo:
            PDF.save_page(
                hid,
                aid,
                payload["page"],
                payload["pages"],
                telegram_id=(
                    msg.photo[-1].file_id
                ),
            )
    except Exception as exc:
        print(
            "HW6 TG CACHE:",
            repr(exc),
            flush=True,
        )

    return msg


async def _edit_page(
    q,
    hid,
    aid,
    page,
):
    hw = _hw(
        hid
    )

    payload = await _payload(
        hid,
        aid,
        page,
    )

    if payload["file_id"]:
        media = InputMediaPhoto(
            media=payload[
                "file_id"
            ],
            caption=_caption(
                hw,
                payload["page"],
                payload["pages"],
            ),
        )
    else:
        media = InputMediaPhoto(
            media=InputFile(
                BytesIO(
                    payload["bytes"]
                ),
                filename=(
                    f"homework_{hid}_"
                    f"page_{payload['page']}.jpg"
                ),
            ),
            caption=_caption(
                hw,
                payload["page"],
                payload["pages"],
            ),
        )

    try:
        msg = await q.edit_message_media(
            media=media,
            reply_markup=_markup(
                hid,
                aid,
                payload["page"],
                payload["pages"],
                done=_done(hw),
            ),
        )

    except Exception as exc:
        if (
            "Message is not modified"
            in str(exc)
        ):
            return

        raise

    try:
        if msg and msg.photo:
            PDF.save_page(
                hid,
                aid,
                payload["page"],
                payload["pages"],
                telegram_id=(
                    msg.photo[-1].file_id
                ),
            )
    except Exception:
        pass


async def _original(
    q,
    context,
    hid,
    aid,
):
    row = PDF.attachment(
        hid,
        aid,
    )

    if not row:
        return

    try:
        await FILES.send(
            context.bot,
            q.message.chat_id,
            hid,
            aid,
        )

    except Exception as exc:
        await q.answer(
            f"Не удалось получить файл: {exc}",
            show_alert=True,
        )


def _formula_markup(
    hid,
    aid=None,
    page=1,
):
    rows = []

    for row in _links(
        hid
    )[:8]:
        title = str(
            (
                FORMULA_LIBRARY
                .get(
                    int(row["grade"]),
                    {},
                )
                .get(
                    row["subject"],
                    {},
                )
                .get(
                    row["topic"],
                    {},
                )
                .get(
                    "title",
                    row["topic"],
                )
            )
        )

        rows.append([
            InlineKeyboardButton(
                f"📖 {title}"[:55],
                callback_data=(
                    f"hw6_fc|"
                    f"{hid}|"
                    f"{aid or 0}|"
                    f"{page}|"
                    f"{row['id']}"
                ),
            )
        ])

    if aid:
        rows.append([
            InlineKeyboardButton(
                "📄 Вернуться к ДЗ",
                callback_data=(
                    f"hw6_home|"
                    f"{hid}|{aid}|{page}"
                ),
            )
        ])
    else:
        rows.append([
            InlineKeyboardButton(
                "⬅️ К ДЗ",
                callback_data="homework",
            )
        ])

    return InlineKeyboardMarkup(
        rows
    )


async def _formula(
    q,
    hid,
    aid=None,
    page=1,
):
    links = _links(
        hid
    )

    if links:
        text = (
            "📚 ФОРМУЛЫ К ДЗ\n\n"
            "Выберите нужный раздел:"
        )
    else:
        text = (
            "📚 ФОРМУЛЫ К ДЗ\n\n"
            "Преподаватель не прикрепил "
            "отдельные формулы."
        )

    if q.message.photo:
        await q.edit_message_caption(
            caption=text,
            reply_markup=_formula_markup(
                hid,
                aid,
                page,
            ),
        )
    else:
        await q.edit_message_text(
            text,
            reply_markup=_formula_markup(
                hid,
                aid,
                page,
            ),
        )


async def _formula_card(
    q,
    hid,
    aid,
    page,
    link_id,
):
    c = database.connect()

    try:
        row = c.execute(
            """
            SELECT *
            FROM homework_formula_links
            WHERE id=?
              AND homework_id=?
            """,
            (
                int(link_id),
                int(hid),
            ),
        ).fetchone()

    finally:
        c.close()

    if not row:
        return

    item = (
        FORMULA_LIBRARY
        .get(
            int(row["grade"]),
            {},
        )
        .get(
            row["subject"],
            {},
        )
        .get(
            row["topic"],
            {},
        )
    )

    title = (
        (item or {}).get(
            "title"
        )
        or row["topic"]
    )

    body = (
        (item or {}).get(
            "text"
        )
        or "Формулы не найдены."
    )

    text = (
        f"📚 {title}\n\n"
        f"{body}"
    )[:980]

    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "◀️ К формулам",
                callback_data=(
                    f"hw6_formula|"
                    f"{hid}|{aid}|{page}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                "📄 К ДЗ",
                callback_data=(
                    f"hw6_home|"
                    f"{hid}|{aid}|{page}"
                ),
            )
        ],
    ])

    if q.message.photo:
        await q.edit_message_caption(
            caption=text,
            reply_markup=markup,
        )
    else:
        await q.edit_message_text(
            text,
            reply_markup=markup,
        )


def _mark_done(
    hid,
):
    c = database.connect()

    try:
        c.execute(
            """
            UPDATE homework
            SET status='DONE'
            WHERE id=?
            """,
            (int(hid),),
        )

        c.commit()

    finally:
        c.close()


async def callback(
    update,
    context,
):
    q = update.callback_query

    if not q:
        return

    data = q.data or ""

    handled = False

    try:
        if (
            data.startswith(("hw6_", "homework_view|", "hw2_student_home|"))
            and q.message.chat_id != q.from_user.id
        ):
            await q.answer("Откройте ДЗ в личном чате с ботом.", show_alert=True)
            raise ApplicationHandlerStop

        if data.startswith("hw6_") and data != "hw6_nop":
            try:
                requested_hid = int(data.split("|", 2)[1])
            except (IndexError, ValueError):
                await q.answer("Некорректная кнопка.", show_alert=True)
                raise ApplicationHandlerStop
            if not _owns(q.from_user.id, requested_hid):
                await q.answer("ДЗ не найдено.", show_alert=True)
                raise ApplicationHandlerStop

        if data.startswith(
            "homework_view|"
        ):
            hid = int(
                data.split("|")[1]
            )

            if not _owns(
                q.from_user.id,
                hid,
            ):
                await q.answer(
                    "ДЗ не найдено",
                    show_alert=True,
                )
            else:
                await q.answer()

                await send_homework(
                    context.bot,
                    q.message.chat_id,
                    hid,
                )

                try:
                    await q.message.delete()
                except Exception:
                    pass

            handled = True

        elif data == "hw6_nop":
            await q.answer()
            handled = True

        elif data.startswith("hw6_file|"):
            try:
                _, hid, aid = data.split("|", 2)
                await FILES.send(
                    context.bot, q.message.chat_id, int(hid), int(aid)
                )
            except Exception as exc:
                await q.answer(f"Не удалось получить файл: {exc}", show_alert=True)
            else:
                await q.answer("Файл отправлен")
            handled = True

        elif data.startswith(
            "hw6_page|"
        ):
            _, hid, aid, page = (
                data.split(
                    "|",
                    3,
                )
            )

            hid = int(hid)

            if _owns(
                q.from_user.id,
                hid,
            ):
                await q.answer()

                await _edit_page(
                    q,
                    hid,
                    int(aid),
                    int(page),
                )

            handled = True

        elif data.startswith(
            "hw6_home|"
        ):
            _, hid, aid, page = (
                data.split(
                    "|",
                    3,
                )
            )

            await q.answer()

            await _edit_page(
                q,
                int(hid),
                int(aid),
                int(page),
            )

            handled = True

        elif data.startswith(
            "hw6_original|"
        ):
            _, hid, aid = (
                data.split(
                    "|",
                    2,
                )
            )

            await q.answer()

            await _original(
                q,
                context,
                int(hid),
                int(aid),
            )

            handled = True

        elif data.startswith(
            "hw6_formula|"
        ):
            _, hid, aid, page = (
                data.split(
                    "|",
                    3,
                )
            )

            await q.answer()

            await _formula(
                q,
                int(hid),
                int(aid),
                int(page),
            )

            handled = True

        elif data.startswith(
            "hw6_formula_text|"
        ):
            hid = int(
                data.split("|")[1]
            )

            await q.answer()

            await _formula(
                q,
                hid,
            )

            handled = True

        elif data.startswith(
            "hw6_fc|"
        ):
            _, hid, aid, page, lid = (
                data.split(
                    "|",
                    4,
                )
            )

            await q.answer()

            await _formula_card(
                q,
                int(hid),
                int(aid),
                int(page),
                int(lid),
            )

            handled = True

        elif data.startswith(
            "hw6_done|"
        ):
            _, hid, aid, page = (
                data.split(
                    "|",
                    3,
                )
            )

            _mark_done(
                int(hid)
            )

            await q.answer(
                "✅ ДЗ выполнено"
            )

            await _edit_page(
                q,
                int(hid),
                int(aid),
                int(page),
            )

            handled = True

        elif data.startswith(
            "hw6_done_text|"
        ):
            hid = int(
                data.split("|")[1]
            )

            _mark_done(
                hid
            )

            await q.answer(
                "✅ ДЗ выполнено"
            )

            handled = True

        # Compatibility with previously created
        # V4/V5 buttons.
        elif data.startswith(
            "hw2_student_home|"
        ):
            hid = int(
                data.split("|")[1]
            )

            if not _owns(q.from_user.id, hid):
                await q.answer("ДЗ не найдено.", show_alert=True)
                handled = True
                return

            await q.answer()

            await send_homework(
                context.bot,
                q.message.chat_id,
                hid,
            )

            handled = True

    finally:
        if handled:
            # Absolutely no legacy handler after this.
            raise ApplicationHandlerStop


def install(
    application,
):
    if getattr(
        application,
        "_homework_v6_installed",
        False,
    ):
        return

    application.add_handler(
        CallbackQueryHandler(
            callback,
            pattern=(
                r"^(?:"
                r"homework_view\|"
                r"|hw6_"
                r"|hw2_student_home\|"
                r")"
            ),
        ),
        group=-50,
    )

    application._homework_v6_installed = True


async def deliver_new(
    bot,
    homework_id,
):
    """
    First page is generated during assignment,
    so later opening is instant.
    """

    hw = _hw(
        homework_id
    )

    if not hw:
        return

    user = database.get_user(
        int(hw["user_id"])
    )

    if (
        user
        and user["telegram_id"]
    ):
        try:
            await send_homework(
                bot,
                int(user["telegram_id"]),
                int(homework_id),
            )
        except Exception as exc:
            print(
                "HW6 NEW TG:",
                repr(exc),
                flush=True,
            )

    # Same preview for VK.
    try:
        from vk_adapter import (
            homework_v6 as VKHW
        )

        import vk_adapter.app as vk_app

        VKHW.deliver(
            vk_app,
            int(homework_id),
            int(hw["user_id"]),
            also_telegram=False,
        )

    except Exception as exc:
        print(
            "HW6 NEW VK:",
            repr(exc),
            flush=True,
        )
