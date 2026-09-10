from __future__ import annotations

import json
import random

import database
import homework_pdf_runtime as PDF

from formula_library import (
    FORMULA_LIBRARY,
)

from . import attachment_bridge as bridge


def _send(
    app,
    peer,
    text,
    rows=None,
    attachment=None,
):
    params = {
        "peer_id": int(peer),
        "random_id": random.randint(
            1,
            2_000_000_000,
        ),
        "message": str(
            text or ""
        ),
    }

    if attachment:
        params[
            "attachment"
        ] = str(attachment)

    if rows:
        params[
            "keyboard"
        ] = app._keyboard_rows(
            rows
        )

    return app.api(
        "messages.send",
        **params,
    )


def _button(
    app,
    label,
    command,
    color="secondary",
):
    return app._button(
        label,
        command,
        color,
    )


def _owns(
    uid,
    hid,
):
    hw = database.get_homework(
        int(hid)
    )

    return bool(
        hw
        and int(hw["user_id"])
        == int(uid)
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


def _caption(
    hw,
    page=None,
    pages=None,
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

    if page is not None:
        lines += [
            "",
            f"📄 Страница "
            f"{page} из {pages}",
        ]

    return "\n".join(
        lines
    )[:3500]


def _rows(
    app,
    hid,
    aid,
    page,
    pages,
    done=False,
):
    nav = []

    if page > 1:
        nav.append(
            _button(
                app,
                "◀️",
                (
                    f"vkhwp|{hid}|"
                    f"{aid}|{page - 1}"
                ),
            )
        )

    nav.append(
        _button(
            app,
            f"{page}/{pages}",
            "vkhwnop",
        )
    )

    if page < pages:
        nav.append(
            _button(
                app,
                "▶️",
                (
                    f"vkhwp|{hid}|"
                    f"{aid}|{page + 1}"
                ),
            )
        )

    return [
        nav,

        [
            _button(
                app,
                "📄 Оригинал PDF",
                f"vkhwo|{hid}|{aid}",
            )
        ],

        [
            _button(
                app,
                "📚 Формулы",
                (
                    f"vkhwf|{hid}|"
                    f"{aid}|{page}"
                ),
            ),

            _button(
                app,
                (
                    "✅ Выполнено"
                    if not done
                    else "✅ Готово"
                ),
                (
                    f"vkhwd|{hid}|"
                    f"{aid}|{page}"
                ),
                "positive",
            ),
        ],

        [
            _button(
                app,
                "⬅️ К ДЗ",
                "homework",
            ),
            _button(
                app,
                "🏠 Главная",
                "home",
            ),
        ],
    ]


def menu(
    app,
    peer,
    uid,
):
    rows = (
        database
        .get_student_homework(
            int(uid),
            active_only=True,
        )
    )

    if not rows:
        _send(
            app,
            peer,
            "📝 Активных домашних "
            "заданий нет.",
            [[
                _button(
                    app,
                    "🏠 Главная",
                    "home",
                )
            ]],
        )

        return

    kb = []

    for hw in rows[:20]:
        title = (
            hw["title"]
            or f"ДЗ #{hw['id']}"
        )

        kb.append([
            _button(
                app,
                f"📝 {title}"[:38],
                f"vkhw|{hw['id']}",
                "primary",
            )
        ])

    kb.append([
        _button(
            app,
            "🏠 Главная",
            "home",
        )
    ])

    _send(
        app,
        peer,
        "📝 ДОМАШНИЕ ЗАДАНИЯ\n\n"
        "Выбери задание:",
        kb,
    )


def _vk_preview(
    peer,
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
            "vk_attachment_key"
        ]
    ):
        return (
            cached[
                "vk_attachment_key"
            ],
            int(
                cached["page_number"]
            ),
            int(
                cached["page_count"]
            ),
        )

    result = PDF.render_page(
        hid,
        aid,
        page,
    )

    key = bridge._vk_upload_photo(
        int(peer),
        result["bytes"],
        (
            f"homework_{hid}_"
            f"page_{result['page']}.jpg"
        ),
        "image/jpeg",
    )

    PDF.save_page(
        hid,
        aid,
        result["page"],
        result["pages"],
        vk_key=key,
    )

    return (
        key,
        result["page"],
        result["pages"],
    )


def open_homework(
    app,
    peer,
    uid,
    hid,
    page=1,
    aid=None,
):
    hid = int(hid)

    if not _owns(
        uid,
        hid,
    ):
        _send(
            app,
            peer,
            "ДЗ не найдено.",
        )
        return

    hw = database.get_homework(
        hid
    )

    ats = PDF.attachments(
        hid
    )

    if not ats:
        _send(
            app,
            peer,
            _caption(hw),
            [[
                _button(
                    app,
                    "📚 Формулы",
                    f"vkhwft|{hid}",
                ),
                _button(
                    app,
                    "✅ Выполнено",
                    f"vkhwdt|{hid}",
                    "positive",
                ),
            ], [
                _button(
                    app,
                    "⬅️ К ДЗ",
                    "homework",
                )
            ]],
        )

        return

    row = (
        PDF.attachment(
            hid,
            aid,
        )
        if aid
        else ats[0]
    )

    if not row:
        return

    if not PDF.is_pdf(
        row
    ):
        key = (
            row["vk_attachment_key"]
            if (
                "vk_attachment_key"
                in row.keys()
            )
            else None
        )

        if not key:
            fid = PDF.telegram_file_id(
                row
            )

            if fid:
                data = (
                    bridge
                    .telegram_file_bytes(
                        fid
                    )
                )

                kind = str(
                    (
                        row["file_type"]
                        if "file_type"
                        in row.keys()
                        else ""
                    )
                    or "document"
                ).lower()

                if kind == "photo":
                    key = (
                        bridge
                        ._vk_upload_photo(
                            int(peer),
                            data,
                            PDF.attachment_filename(
                                row
                            ),
                            (
                                row["mime_type"]
                                if "mime_type"
                                in row.keys()
                                else None
                            )
                            or "image/jpeg",
                        )
                    )
                else:
                    key = (
                        bridge
                        ._vk_upload_document(
                            int(peer),
                            data,
                            PDF.attachment_filename(
                                row
                            ),
                            (
                                row["mime_type"]
                                if "mime_type"
                                in row.keys()
                                else None
                            ),
                        )
                    )

        _send(
            app,
            peer,
            _caption(hw),
            [[
                _button(
                    app,
                    "📚 Формулы",
                    f"vkhwft|{hid}",
                ),
                _button(
                    app,
                    "✅ Выполнено",
                    f"vkhwdt|{hid}",
                    "positive",
                ),
            ], [
                _button(
                    app,
                    "⬅️ К ДЗ",
                    "homework",
                )
            ]],
            key,
        )

        return

    aid = int(
        row["id"]
    )

    try:
        key, page, pages = (
            _vk_preview(
                peer,
                hid,
                aid,
                page,
            )
        )

        _send(
            app,
            peer,
            _caption(
                hw,
                page,
                pages,
            ),
            _rows(
                app,
                hid,
                aid,
                page,
                pages,
                done=_done(hw),
            ),
            key,
        )

    except Exception as exc:
        _send(
            app,
            peer,
            (
                "⚠️ Не удалось открыть "
                "preview PDF.\n\n"
                f"{exc}"
            ),
            [[
                _button(
                    app,
                    "📄 Оригинал",
                    f"vkhwo|{hid}|{aid}",
                )
            ]],
        )


def original(
    app,
    peer,
    uid,
    hid,
    aid,
):
    if not _owns(
        uid,
        hid,
    ):
        return

    row = PDF.attachment(
        hid,
        aid,
    )

    if not row:
        return

    key = (
        row["vk_attachment_key"]
        if (
            "vk_attachment_key"
            in row.keys()
        )
        else None
    )

    if not key:
        try:
            source = PDF.ensure_source(
                row
            )

            data = source.read_bytes()

            key = (
                bridge
                ._vk_upload_document(
                    int(peer),
                    data,
                    PDF.attachment_filename(
                        row
                    ),
                    "application/pdf",
                )
            )

            c = database.connect()

            try:
                c.execute(
                    """
                    UPDATE homework_attachments
                    SET vk_attachment_key=?
                    WHERE id=?
                    """,
                    (
                        key,
                        int(aid),
                    ),
                )

                c.commit()

            finally:
                c.close()

        except Exception as exc:
            _send(
                app,
                peer,
                f"❌ PDF недоступен: {exc}",
            )

            return

    _send(
        app,
        peer,
        "📄 Оригинал ДЗ",
        [[
            _button(
                app,
                "⬅️ К ДЗ",
                f"vkhw|{hid}",
            )
        ]],
        key,
    )


def formulas(
    app,
    peer,
    uid,
    hid,
    aid=0,
    page=1,
):
    if not _owns(
        uid,
        hid,
    ):
        return

    c = database.connect()

    try:
        links = list(
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

    rows = []

    for row in links[:10]:
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

        rows.append([
            _button(
                app,
                f"📖 {title}"[:38],
                (
                    f"vkhwfc|{hid}|"
                    f"{aid}|{page}|"
                    f"{row['id']}"
                ),
            )
        ])

    if aid:
        rows.append([
            _button(
                app,
                "📄 К ДЗ",
                (
                    f"vkhwp|{hid}|"
                    f"{aid}|{page}"
                ),
            )
        ])
    else:
        rows.append([
            _button(
                app,
                "⬅️ К ДЗ",
                f"vkhw|{hid}",
            )
        ])

    _send(
        app,
        peer,
        (
            "📚 ФОРМУЛЫ К ДЗ\n\n"
            + (
                "Выбери раздел:"
                if links
                else (
                    "Преподаватель не "
                    "прикрепил формулы."
                )
            )
        ),
        rows,
    )


def formula_card(
    app,
    peer,
    uid,
    hid,
    aid,
    page,
    link_id,
):
    if not _owns(
        uid,
        hid,
    ):
        return

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

    text = (
        (item or {}).get(
            "text"
        )
        or "Формулы не найдены."
    )

    _send(
        app,
        peer,
        (
            f"📚 {title}\n\n"
            f"{text}"
        )[:3500],
        [[
            _button(
                app,
                "◀️ К формулам",
                (
                    f"vkhwf|{hid}|"
                    f"{aid}|{page}"
                ),
            )
        ], [
            _button(
                app,
                "📄 К ДЗ",
                (
                    f"vkhwp|{hid}|"
                    f"{aid}|{page}"
                ),
            )
        ]],
    )


def mark_done(
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


def _tg_keyboard(
    hid,
    aid,
    page,
    pages,
):
    return json.dumps(
        {
            "inline_keyboard": [
                [
                    {
                        "text": "◀️",
                        "callback_data": (
                            f"hw6_page|{hid}|"
                            f"{aid}|"
                            f"{max(1,page-1)}"
                        ),
                    },
                    {
                        "text": f"{page}/{pages}",
                        "callback_data": "hw6_nop",
                    },
                    {
                        "text": "▶️",
                        "callback_data": (
                            f"hw6_page|{hid}|"
                            f"{aid}|"
                            f"{min(pages,page+1)}"
                        ),
                    },
                ],
                [
                    {
                        "text": "📄 Оригинал PDF",
                        "callback_data": (
                            f"hw6_original|"
                            f"{hid}|{aid}"
                        ),
                    }
                ],
                [
                    {
                        "text": "📚 Формулы",
                        "callback_data": (
                            f"hw6_formula|"
                            f"{hid}|{aid}|{page}"
                        ),
                    },
                    {
                        "text": "✅ Выполнено",
                        "callback_data": (
                            f"hw6_done|"
                            f"{hid}|{aid}|{page}"
                        ),
                    },
                ],
            ]
        },
        ensure_ascii=False,
    )


def _send_tg_preview(
    hid,
    uid,
):
    user = database.get_user(
        int(uid)
    )

    if (
        not user
        or not user["telegram_id"]
    ):
        return

    ats = PDF.attachments(
        hid
    )

    if (
        not ats
        or not PDF.is_pdf(
            ats[0]
        )
    ):
        return

    row = ats[0]

    aid = int(
        row["id"]
    )

    cached = PDF.cached_page(
        aid,
        1,
    )

    if (
        cached
        and cached[
            "telegram_file_id"
        ]
    ):
        payload = {
            "chat_id": int(
                user["telegram_id"]
            ),
            "photo": cached[
                "telegram_file_id"
            ],
            "caption": (
                "📝 ДОМАШНЕЕ ЗАДАНИЕ\n\n"
                "📄 Страница 1 из "
                f"{cached['page_count']}"
            ),
            "reply_markup": _tg_keyboard(
                hid,
                aid,
                1,
                int(
                    cached[
                        "page_count"
                    ]
                ),
            ),
        }

        bridge._json_request(
            (
                "https://api.telegram.org/"
                f"bot{bridge.BOT_TOKEN}/"
                "sendPhoto"
            ),
            payload,
        )

        return

    result = PDF.render_page(
        hid,
        aid,
        1,
    )

    body, form_type = bridge._multipart(
        {
            "chat_id": int(
                user["telegram_id"]
            ),
            "caption": (
                "📝 ДОМАШНЕЕ ЗАДАНИЕ\n\n"
                f"📄 Страница 1 из "
                f"{result['pages']}"
            ),
            "reply_markup": _tg_keyboard(
                hid,
                aid,
                1,
                result["pages"],
            ),
        },
        [
            (
                "photo",
                f"homework_{hid}_1.jpg",
                result["bytes"],
                "image/jpeg",
            )
        ],
    )

    response = bridge._json_request(
        (
            "https://api.telegram.org/"
            f"bot{bridge.BOT_TOKEN}/"
            "sendPhoto"
        ),
        body,
        {
            "Content-Type": form_type
        },
        timeout=90,
    )

    try:
        photos = (
            response["result"]["photo"]
        )

        fid = (
            photos[-1]["file_id"]
        )

        PDF.save_page(
            hid,
            aid,
            1,
            result["pages"],
            telegram_id=fid,
        )

    except Exception:
        pass


def deliver(
    app,
    hid,
    uid,
    also_telegram=False,
):
    try:
        peer = bridge._vk_peer(
            int(uid)
        )

        if peer:
            open_homework(
                app,
                int(peer),
                int(uid),
                int(hid),
                1,
            )

    except Exception as exc:
        print(
            "HW6 VK DELIVERY:",
            repr(exc),
            flush=True,
        )

    if also_telegram:
        try:
            _send_tg_preview(
                int(hid),
                int(uid),
            )
        except Exception as exc:
            print(
                "HW6 VK->TG PREVIEW:",
                repr(exc),
                flush=True,
            )
