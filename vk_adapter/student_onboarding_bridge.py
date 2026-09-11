from __future__ import annotations

import json
import random
import re

from core import event_center
from web_backend import student_onboarding, public_trial_channel, trial_followup

JOIN_RE = re.compile(r"\bJOIN-[A-Z0-9]{10}\b", re.I)
TRIAL_RE = re.compile(r"\bTRIAL-[A-Z0-9]{10}\b", re.I)
_PENDING_MESSAGE = set()


def extract_token(text):
    raw = str(text or '').upper()
    m = JOIN_RE.search(raw)
    if m:
        return ('JOIN', m.group(0).upper())
    m = TRIAL_RE.search(raw)
    if m:
        return ('TRIAL', m.group(0).upper())
    return (None, None)


def _button(label, command, color='secondary'):
    return {'action': {'type': 'text', 'label': label, 'payload': json.dumps({'command': command}, ensure_ascii=False)}, 'color': color}


def _link(label, url):
    return {'action': {'type': 'open_link', 'label': label, 'link': str(url)}}


def _trial_keyboard(row):
    status = str(row.get('status') or '').upper()
    rows = []
    if row.get('meeting_url') and status != 'TRIAL_COMPLETED':
        rows.append([_link('▶️ Подключиться к занятию', row['meeting_url'])])
    if row.get('board_url'):
        rows.append([_link('📝 Открыть доску', row['board_url'])])
    if status == 'TRIAL_COMPLETED':
        rows.append([_button('💜 Продолжить заниматься', 'trial_guest|continue', 'positive')])
        rows.append([_button('🕒 Хочу подумать', 'trial_guest|thinking')])
        rows.append([_button('Пока не планирую', 'trial_guest|stop', 'negative')])
    else:
        rows.append([_button('🎓 Моё пробное', 'trial_guest|home', 'primary')])
        rows.append([_button('💬 Преподаватель', 'trial_guest|message')])
    return json.dumps({'one_time': False, 'inline': False, 'buttons': rows}, ensure_ascii=False)


def _send_trial(app_module, peer_id, text, row):
    return app_module.api(
        'messages.send',
        peer_id=int(peer_id),
        random_id=random.randint(1, 2_000_000_000),
        message=str(text),
        keyboard=_trial_keyboard(row),
    )


def _send_plain(app_module, peer_id, text, buttons=None):
    params = {
        'peer_id': int(peer_id),
        'random_id': random.randint(1, 2_000_000_000),
        'message': str(text),
    }
    if buttons:
        params['keyboard'] = json.dumps({'one_time': False, 'inline': False, 'buttons': buttons}, ensure_ascii=False)
    return app_module.api('messages.send', **params)


def _trial_text(row):
    status = str(row.get('status') or 'NEW').upper()
    status_text = {
        'NEW': 'ожидает подтверждения',
        'CONTACTED': 'преподаватель увидел заявку',
        'ACCEPTED': 'подтверждено',
        'TRIAL_COMPLETED': 'пробное завершено',
        'CONVERTED': 'вы стали постоянным учеником',
    }.get(status, status.lower())
    start = row.get('trial_start') or row.get('selected_slot_start')
    lines = [
        '💜 АДЕЛИЯ • ПРОБНОЕ',
        '',
        f"👤 {row.get('name') or 'Ученик'}",
        f"📚 {row.get('subject') or 'Занятие'}",
        f'Статус: {status_text}',
    ]
    if start:
        lines.append(f"🕐 {str(start).replace('T', ' ')[:16]}")
    if status == 'TRIAL_COMPLETED':
        lines += ['', 'Как тебе формат? Выбери, что делать дальше 👇']
    else:
        lines.append('🎥 Ссылка на занятие готова' if row.get('meeting_url') else '🎥 Ссылка появится после подтверждения преподавателем')
        if row.get('board_url'):
            lines.append('📝 Доска готова')
        lines += ['', 'Пока доступен только режим пробного занятия.']
    return '\n'.join(lines)


def _command(message):
    payload = message.get('payload')
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = None
    if isinstance(payload, dict):
        cmd = payload.get('command') or payload.get('cmd')
        if cmd:
            return str(cmd)
    text = ' '.join(str(message.get('text') or '').strip().lower().split())
    mapping = {
        '🎓 моё пробное': 'trial_guest|home',
        '💬 преподаватель': 'trial_guest|message',
        '💜 продолжить заниматься': 'trial_guest|continue',
        '🕒 хочу подумать': 'trial_guest|thinking',
        'пока не планирую': 'trial_guest|stop',
        'привет': 'trial_guest|home',
        'начать': 'trial_guest|home',
        'start': 'trial_guest|home',
        '/start': 'trial_guest|home',
    }
    return mapping.get(text, '')


def _relay_to_teacher(row, text):
    clean = str(text or '').strip()[:1500]
    if not clean:
        return
    try:
        event_center.push(
            'PUBLIC_TRIAL_MESSAGE',
            f"Сообщение от пробника: {row.get('name') or 'Без имени'}",
            clean,
            'ACTION',
            'public_trial',
            int(row['id']),
            f"public_trial_vk_message:{int(row['id'])}:{abs(hash(clean)) % 1000000}",
        )
    except Exception as exc:
        print('VK TRIAL MESSAGE EVENT ERROR:', repr(exc), flush=True)


def _handle_trial_guest(app_module, message, row):
    vk_id = int(message.get('from_id') or 0)
    peer_id = int(message.get('peer_id') or vk_id)
    cmd = _command(message)
    raw = str(message.get('text') or '').strip()

    if cmd == 'trial_guest|message':
        _PENDING_MESSAGE.add(vk_id)
        _send_trial(app_module, peer_id, '💬 Напишите следующим сообщением то, что хотите передать преподавателю.', row)
        return True

    if cmd in {'trial_guest|continue', 'trial_guest|thinking', 'trial_guest|stop'}:
        choice = {
            'trial_guest|continue': 'CONTINUE',
            'trial_guest|thinking': 'THINKING',
            'trial_guest|stop': 'STOP',
        }[cmd]
        try:
            trial_followup.decide(int(row['id']), choice)
        except ValueError as exc:
            _send_trial(app_module, peer_id, f'Не удалось сохранить решение: {exc}', row)
            return True
        if choice == 'CONTINUE':
            buttons = [[_link('Продолжить регистрацию →', f"https://adeliatutor.ru/onboarding/?trial={int(row['id'])}")]]
            _send_plain(
                app_module,
                peer_id,
                '💜 Отлично! Данные пробного сохранены.\n\nОткрой сайт Аделии и заверши создание постоянного аккаунта — имя, класс, предмет и контакт повторно вводить не придётся.',
                buttons,
            )
        elif choice == 'THINKING':
            _send_plain(
                app_module,
                peer_id,
                '🕒 Хорошо. Я сохраню пробное и напомню через несколько дней. Если решишь раньше — просто снова напиши сюда.',
                [[_button('🎓 Моё пробное', 'trial_guest|home', 'primary')]],
            )
        else:
            _send_plain(
                app_module,
                peer_id,
                'Спасибо, что попробовали формат 💜\n\nПробное завершено. Постоянный аккаунт создавать не будем.',
            )
        return True

    if cmd == 'trial_guest|home':
        _PENDING_MESSAGE.discard(vk_id)
        _send_trial(app_module, peer_id, _trial_text(row), row)
        return True

    if vk_id in _PENDING_MESSAGE:
        _PENDING_MESSAGE.discard(vk_id)
        if raw:
            _relay_to_teacher(row, raw)
            _send_trial(app_module, peer_id, '✅ Сообщение передано преподавателю.', row)
        else:
            _send_trial(app_module, peer_id, 'Пришлите текстовым сообщением то, что хотите передать преподавателю.', row)
        return True

    _send_trial(app_module, peer_id, _trial_text(row), row)
    return True


def handle_message(app_module, message):
    """Handle JOIN/TRIAL codes and keep verified public-trial users in guest mode."""
    kind, token = extract_token(message.get('text'))
    vk_id = int(message.get('from_id') or 0)
    peer_id = int(message.get('peer_id') or vk_id)
    if vk_id <= 0:
        return False

    if not token:
        try:
            row = public_trial_channel.pending_by_external('VK', str(vk_id))
        except Exception:
            row = None
        if row:
            return _handle_trial_guest(app_module, message, row)
        return False

    try:
        profile = app_module._profile(vk_id)
        if kind == 'TRIAL':
            public_trial_channel.confirm(
                token,
                'VK',
                str(vk_id),
                username=profile.get('username'),
                display_name=profile.get('display_name'),
            )
            row = public_trial_channel.pending_by_external('VK', str(vk_id))
            app_module.send(peer_id, '✅ ВКонтакте подключён к пробному занятию 💜', linked=False)
            if row:
                _send_trial(app_module, peer_id, _trial_text(row), row)
            return True

        payload = student_onboarding.confirm_channel(
            token,
            'VK',
            str(vk_id),
            username=profile.get('username'),
            display_name=profile.get('display_name'),
        )
        name = (payload.get('user') or {}).get('name') or payload.get('name') or 'ученик'
        app_module.send(
            peer_id,
            f"✅ ВКонтакте подключён, {name}!\n\n"
            'Вернитесь на страницу регистрации Аделии — она автоматически продолжится.\n\n'
            'До завершения регистрации обычное меню ученика здесь не откроется.',
            linked=False,
        )
    except ValueError as exc:
        code = str(exc)
        if kind == 'TRIAL':
            if code in {'trial_link_expired', 'trial_link_not_found'}:
                text = 'Код пробного истёк. Вернитесь на сайт Аделии и создайте новую привязку 💜'
            elif code == 'wrong_channel':
                text = 'Этот код создан для другого способа подключения. Вернитесь на сайт и выберите VK.'
            else:
                text = 'Не удалось подключить VK к пробному. Проверьте код и попробуйте ещё раз.'
        else:
            if code in {'onboarding_expired', 'onboarding_not_found'}:
                text = 'Код регистрации истёк. Вернитесь на сайт Аделии и начните регистрацию заново 💜'
            elif code == 'wrong_channel':
                text = 'Этот код создан для другого способа подключения. Вернитесь на сайт и выберите VK.'
            else:
                text = 'Не удалось подтвердить VK. Проверьте код и попробуйте ещё раз.'
        app_module.send(peer_id, text, linked=False)
    except Exception as exc:
        print('VK ONBOARDING ERROR:', repr(exc), flush=True)
        app_module.send(peer_id, 'Не удалось подтвердить VK. Попробуйте ещё раз чуть позже.', linked=False)
    return True
