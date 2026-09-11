from __future__ import annotations

import re

from web_backend import student_onboarding, public_trial_channel

JOIN_RE = re.compile(r"\bJOIN-[A-Z0-9]{10}\b", re.I)
TRIAL_RE = re.compile(r"\bTRIAL-[A-Z0-9]{10}\b", re.I)


def extract_token(text):
    raw = str(text or '').upper()
    m = JOIN_RE.search(raw)
    if m:
        return ('JOIN', m.group(0).upper())
    m = TRIAL_RE.search(raw)
    if m:
        return ('TRIAL', m.group(0).upper())
    return (None, None)


def handle_message(app_module, message):
    """Handle returning-student JOIN codes and public-trial TRIAL codes.

    Returns True when the message belongs to onboarding/trial linking and has been consumed.
    """
    kind, token = extract_token(message.get('text'))
    if not token:
        return False

    vk_id = int(message.get('from_id') or 0)
    peer_id = int(message.get('peer_id') or vk_id)
    if vk_id <= 0:
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
            app_module.send(
                peer_id,
                "✅ ВКонтакте подключён к пробному занятию 💜\n\n"
                "Теперь сюда смогут прийти подтверждение времени, ссылка на занятие и важные изменения.\n\n"
                "Полное меню ученика появится только если после пробного вы решите продолжить занятия.",
                linked=False,
            )
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
            "Вернитесь на страницу регистрации Аделии — она автоматически продолжится.\n\n"
            "До завершения регистрации обычное меню ученика здесь не откроется.",
            linked=False,
        )
    except ValueError as exc:
        code = str(exc)
        if kind == 'TRIAL':
            if code in {'trial_link_expired','trial_link_not_found'}:
                text = 'Код пробного истёк. Вернитесь на сайт Аделии и создайте новую привязку 💜'
            elif code == 'wrong_channel':
                text = 'Этот код создан для другого способа подключения. Вернитесь на сайт и выберите VK.'
            else:
                text = 'Не удалось подключить VK к пробному. Проверьте код и попробуйте ещё раз.'
        else:
            if code in {'onboarding_expired','onboarding_not_found'}:
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
