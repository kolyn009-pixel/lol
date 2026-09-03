from __future__ import annotations

import json
import os
import random
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import database
from . import schema, service, notification_sync

API_VERSION = os.getenv("VK_API_VERSION", "5.199").strip() or "5.199"
GROUP_ID = os.getenv("VK_GROUP_ID", "").strip()
TOKEN = os.getenv("VK_TOKEN", "").strip()


def _http_json(url, data=None, timeout=35):
    body = None
    headers = {"User-Agent": "TutorBot-VK/1.0"}
    if data is not None:
        body = urlencode(data).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = Request(url, data=body, headers=headers)
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def api(method, **params):
    if not TOKEN:
        raise RuntimeError("VK_TOKEN is not configured")
    payload = dict(params)
    payload["access_token"] = TOKEN
    payload["v"] = API_VERSION
    data = _http_json(f"https://api.vk.com/method/{method}", payload)
    if "error" in data:
        raise RuntimeError(f"VK API {method}: {data['error']}")
    return data.get("response")


def _button(label, command, color="secondary"):
    return {
        "action": {
            "type": "text",
            "label": label,
            "payload": json.dumps({"command": command}, ensure_ascii=False),
        },
        "color": color,
    }


def keyboard(linked=False):
    if not linked:
        buttons = [
            [_button("🔗 Связать с Telegram", "link_help", "primary")],
            [_button("ℹ️ Как это работает", "help")],
        ]
    else:
        buttons = [
            [_button("📅 Моё расписание", "schedule", "primary")],
            [_button("🏠 Главное меню", "home")],
            [_button("🔗 Связь с Telegram", "linked")],
        ]
    return json.dumps({"one_time": False, "inline": False, "buttons": buttons}, ensure_ascii=False)


def send(peer_id, text, linked=False):
    return api(
        "messages.send",
        peer_id=int(peer_id),
        random_id=random.randint(1, 2_000_000_000),
        message=str(text),
        keyboard=keyboard(linked=linked),
    )


def _extract_command(message):
    payload = message.get("payload")
    if payload:
        try:
            obj = json.loads(payload) if isinstance(payload, str) else payload
            return str(obj.get("command") or "").strip().lower()
        except Exception:
            pass
    text = str(message.get("text") or "").strip().lower()
    mapping = {
        "📅 моё расписание": "schedule",
        "🏠 главное меню": "home",
        "🔗 связь с telegram": "linked",
        "🔗 связать с telegram": "link_help",
        "ℹ️ как это работает": "help",
        "привет": "home",
        "начать": "home",
        "start": "home",
        "/start": "home",
    }
    return mapping.get(text, text)


def _profile(vk_id):
    try:
        rows = api("users.get", user_ids=int(vk_id), fields="screen_name") or []
        if rows:
            row = rows[0]
            return {
                "display_name": (f"{row.get('first_name','')} {row.get('last_name','')}").strip(),
                "username": row.get("screen_name"),
            }
    except Exception:
        pass
    return {"display_name": None, "username": None}


def handle_message(message):
    vk_id = int(message.get("from_id") or 0)
    peer_id = int(message.get("peer_id") or vk_id)
    if vk_id <= 0:
        return

    user = service.linked_user(vk_id)
    command = _extract_command(message)
    raw_text = str(message.get("text") or "").strip()

    if raw_text.upper().replace(" ", "").startswith("ADELIA-"):
        profile = _profile(vk_id)
        user_id, error = schema.consume_link_code(
            raw_text,
            "VK",
            str(vk_id),
            username=profile.get("username"),
            display_name=profile.get("display_name"),
        )
        if error:
            send(peer_id, f"❌ {error}", linked=False)
            return
        linked_user = database.get_user(int(user_id))
        send(
            peer_id,
            "✅ VK подключён к TutorBot.\n\n"
            f"Теперь это одна карточка ученика: {linked_user['name']}.\n"
            "Расписание, занятия, оплаты и баланс общие для Telegram и VK.\n\n"
            "Важные напоминания о занятиях и ссылка перед уроком будут дублироваться сюда.",
            linked=True,
        )
        return

    if not user:
        if command == "help":
            send(
                peer_id,
                "VK работает как второй вход в TutorBot.\n\n"
                "Если ты уже зарегистрирован в Telegram, получи там одноразовый код командой /vklink и отправь его сюда.",
                linked=False,
            )
        else:
            send(
                peer_id,
                "💜 АДЕЛИЯ\n\n"
                "Чтобы не создавать второго ученика, сначала свяжем VK с существующей карточкой TutorBot.\n"
                "В Telegram отправь /vklink, затем пришли полученный код сюда.",
                linked=False,
            )
        return

    if command == "schedule":
        send(peer_id, service.upcoming_text(int(user["id"])), linked=True)
        return
    if command == "linked":
        send(
            peer_id,
            f"✅ VK связан с карточкой «{user['name']}».\n"
            "Telegram и VK используют одну базу занятий и оплат.",
            linked=True,
        )
        return

    send(
        peer_id,
        f"💜 {user['name']}, привет!\n\n"
        "VK подключён к твоему TutorBot. Выбери действие кнопками ниже.",
        linked=True,
    )


def long_poll_server():
    data = api("groups.getLongPollServer", group_id=GROUP_ID)
    return data["server"], data["key"], data["ts"]


def run_forever():
    if not GROUP_ID or not TOKEN:
        raise SystemExit("VK_GROUP_ID/VK_TOKEN are not configured")
    schema.initialize()
    notification_sync.initialize()
    server, key, ts = long_poll_server()
    print(f"VK LONG POLL START group={GROUP_ID} api={API_VERSION}")
    last_notification_tick = 0.0

    while True:
        try:
            data = _http_json(
                f"{server}?" + urlencode({"act": "a_check", "key": key, "ts": ts, "wait": 25}),
                timeout=35,
            )
            if data.get("failed"):
                server, key, ts = long_poll_server()
                continue
            ts = data.get("ts", ts)
            for update in data.get("updates", []):
                if update.get("type") == "message_new":
                    obj = update.get("object") or {}
                    message = obj.get("message") if isinstance(obj, dict) else None
                    if message:
                        handle_message(message)

            now_mono = time.monotonic()
            if now_mono - last_notification_tick >= 30:
                try:
                    count = notification_sync.tick(send)
                    if count:
                        print("VK NOTIFICATIONS SENT:", count)
                except Exception as exc:
                    print("VK NOTIFICATION ERROR:", repr(exc))
                last_notification_tick = now_mono

        except KeyboardInterrupt:
            raise
        except Exception as exc:
            print("VK LONG POLL ERROR:", repr(exc))
            time.sleep(3)
            try:
                server, key, ts = long_poll_server()
            except Exception:
                time.sleep(5)


if __name__ == "__main__":
    run_forever()
