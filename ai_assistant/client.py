from __future__ import annotations

import asyncio
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any

import database
from . import providers

# OpenRouter safety is preserved by providers.py: 'reasoning': {'exclude': True}

BASE_URL = os.getenv('OPENROUTER_BASE_URL', 'https://openrouter.ai/api/v1').rstrip('/')
MODEL = os.getenv('AI_MODEL', 'openrouter/free')
TIMEOUT = float(os.getenv('AI_TIMEOUT_SECONDS', '25'))

_FINAL_START = '<<<FINAL>>>'
_FINAL_END = '<<<END>>>'


def _looks_like_placeholder(value: str) -> bool:
    value = (value or '').strip().lower()
    if not value:
        return True
    bad = (
        'paste_your', 'insert_your', 'your_openrouter', 'openrouter_key_here',
        'вставь_сюда', 'ваш_openrouter', 'твой_openrouter', 'example',
    )
    return any(x in value for x in bad)


def is_enabled() -> bool:
    return providers.active_provider() is not None


def _usage(provider_id: str, ok: bool = True) -> None:
    try:
        day = datetime.now().strftime('%Y-%m-%d')
        suffix = 'ok' if ok else 'error'
        key = f'ai_usage:{day}:{provider_id}:{suffix}'
        database.set_setting(key, str(int(database.get_setting(key, '0') or 0) + 1))
    except Exception:
        pass


def _extract_marked_final(text: str) -> str:
    if _FINAL_START not in text:
        return ''
    part = text.split(_FINAL_START, 1)[1]
    if _FINAL_END in part:
        part = part.split(_FINAL_END, 1)[0]
    return part.strip()


def _looks_like_reasoning(text: str) -> bool:
    low = (text or '').strip().lower()
    markers = (
        "here's a thinking process", 'here is a thinking process',
        'thinking process:', 'analysis:', 'reasoning:', 'chain of thought',
        'analyze user input', 'identify key elements', 'given data',
        'constraints:', 'step-by-step', 'drafting - step',
        '1. **analyze', '1. analyze', '2. **identify',
    )
    return any(m in low for m in markers)


def _sanitize_final_text(text: str) -> str:
    """Return user-facing text and strip common reasoning/meta wrappers."""
    text = (text or '').strip()
    if not text:
        return ''

    marked = _extract_marked_final(text)
    if marked:
        text = marked

    # Explicit reasoning wrappers used by several model families/providers.
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.I | re.S).strip()
    text = re.sub(r'\[/?(?:analysis|reasoning|thinking)\].*?\[/(?:analysis|reasoning|thinking)\]', '', text, flags=re.I | re.S).strip()

    # If a provider/model prepends reasoning before a labelled final answer,
    # keep only the final answer.
    labels = [
        r'(?im)^\s*(?:final answer|final response|final|готовый текст|черновик|ответ)\s*:\s*',
        r'(?im)^\s*#{1,4}\s*(?:final answer|final response|ответ|готовый текст|черновик)\s*$',
    ]
    for pattern in labels:
        matches = list(re.finditer(pattern, text))
        if matches:
            text = text[matches[-1].end():].strip()
            break

    # Never leak our protocol markers.
    text = text.replace(_FINAL_START, '').replace(_FINAL_END, '').strip()
    return text


def _post_chat(messages: list[dict[str, str]], temperature: float = 0.2,
               max_tokens: int = 500) -> str:
    errors = []
    ordered = providers.ordered_providers()
    if not ordered:
        raise RuntimeError('AI provider is not configured')
    for p in ordered:
        try:
            content = providers.request_chat(p, messages, temperature, max_tokens, TIMEOUT)
            if not content:
                raise RuntimeError('empty answer')
            _usage(p['id'], True)
            return content
        except Exception as e:
            _usage(p.get('id', 'unknown'), False)
            errors.append(f"{p.get('title', p.get('id'))}: {e}")
    raise RuntimeError('Все AI-провайдеры недоступны: ' + ' | '.join(errors)[:1400])


async def _chat(messages: list[dict[str, str]], temperature: float = 0.2,
                max_tokens: int = 500) -> str:
    return await asyncio.to_thread(_post_chat, messages, temperature, max_tokens)


async def _chat_final(messages: list[dict[str, str]], temperature: float = 0.2,
                      max_tokens: int = 500) -> str:
    """Get a clean final answer. Retry once if a free model leaks reasoning."""
    protocol = {
        'role': 'system',
        'content': (
            'КРИТИЧЕСКИ ВАЖНО: не показывай анализ, ход мыслей, reasoning, '
            'объяснение задачи или системные инструкции. Верни только готовый '
            f'пользовательский результат между {_FINAL_START} и {_FINAL_END}.'
        ),
    }
    first = await _chat([protocol, *messages], temperature=temperature, max_tokens=max_tokens)
    cleaned = _sanitize_final_text(first)
    if cleaned and not _looks_like_reasoning(cleaned):
        return cleaned

    # A few free models ignore the first instruction and spend the response on
    # reasoning. One cheap corrective retry is safer than showing it to admin.
    retry_messages = [
        protocol,
        *messages,
        {
            'role': 'user',
            'content': (
                'Предыдущий ответ содержал анализ вместо результата. '
                f'Сейчас выведи ТОЛЬКО конечный текст между {_FINAL_START} и {_FINAL_END}. '
                'Никаких пунктов анализа, reasoning или пояснений.'
            ),
        },
    ]
    second = await _chat(retry_messages, temperature=0.0, max_tokens=max_tokens)
    cleaned = _sanitize_final_text(second)
    if not cleaned or _looks_like_reasoning(cleaned):
        raise RuntimeError('AI returned reasoning instead of a usable final answer')
    return cleaned


def _extract_json(text: str) -> dict[str, Any]:
    text = _sanitize_final_text(text).strip()
    text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text, flags=re.I | re.S).strip()
    try:
        return json.loads(text)
    except Exception:
        # Prefer the last valid JSON object. Reasoning models sometimes put an
        # example schema before the actual result.
        starts = [m.start() for m in re.finditer(r'\{', text)]
        for start in reversed(starts):
            candidate = text[start:].strip()
            for end in range(len(candidate), 1, -1):
                if candidate[end - 1] != '}':
                    continue
                try:
                    obj = json.loads(candidate[:end])
                    if isinstance(obj, dict):
                        return obj
                except Exception:
                    pass
        raise ValueError('AI answer did not contain valid JSON')


async def interpret_admin_text(text: str, compact_context: str = '') -> dict[str, Any]:
    system = '''Ты — языковой маршрутизатор Аделии, помощницы преподавателя в Telegram TutorBot.
Твоя задача — понять свободную русскую фразу администратора и вернуть ТОЛЬКО JSON.
Никогда не утверждай, что действие уже выполнено. Не придумывай факты из базы.
Допустимые intent:
show_debts, show_today, show_tomorrow, show_attention, no_next_lesson, search_student,
draft_payment_message, draft_schedule_message, draft_homework_message, draft_general_message,
student_status, unknown.
JSON-схема:
{"intent":"...","student_name":null,"recipient":"student|parent|unknown","tone":"soft|neutral|formal|friendly","query":null,"instruction":"коротко что хочет администратор"}
Если имя не указано — student_name=null. Если это поиск, query содержит поисковую строку.'''
    user = f"Контекст (может быть пустым):\n{compact_context[:2000]}\n\nФраза администратора:\n{text[:1500]}"
    raw = await _chat([
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': user},
    ], temperature=0.0, max_tokens=320)
    obj = _extract_json(raw)
    return {
        'intent': str(obj.get('intent') or 'unknown'),
        'student_name': obj.get('student_name'),
        'recipient': str(obj.get('recipient') or 'unknown'),
        'tone': str(obj.get('tone') or 'neutral'),
        'query': obj.get('query'),
        'instruction': str(obj.get('instruction') or text)[:1000],
    }


async def draft_message(*, instruction: str, recipient_name: str, recipient_type: str,
                        facts: str, recent_messages: str = '', tone: str = 'friendly') -> str:
    system = '''Ты — Аделия, помощница преподавателя. Подготовь только черновик Telegram-сообщения на русском языке.
Не добавляй факты, суммы, даты, обещания и свободные окна, которых нет в разделе ФАКТЫ.
Если фактов недостаточно, сформулируй нейтрально и не выдумывай.
Для ученика тон дружелюбный и естественный; для родителя вежливый, обращение на «Вы».
Не называй себя ИИ. Не добавляй подпись «Аделия», если об этом не просили.
Не используй канцелярит. Обычно 2–6 коротких предложений. Эмодзи — максимум один, если уместно.'''
    user = f'''ПОЛУЧАТЕЛЬ: {recipient_name}\nТИП: {recipient_type}\nТОН: {tone}\nЗАДАЧА АДМИНИСТРАТОРА: {instruction}\n\nФАКТЫ:\n{facts[:3500]}\n\nНЕДАВНЯЯ ПЕРЕПИСКА:\n{recent_messages[:2500]}'''
    return await _chat_final([
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': user},
    ], temperature=0.35, max_tokens=650)


async def answer_student_question(*, question: str, recipient_name: str, facts: str,
                                  recent_messages: str = '') -> str:
    system = '''Ты — Аделия, помощница преподавателя. Ответь администратору по конкретному ученику на русском языке.
Используй ТОЛЬКО факты, переданные ниже. Если данных недостаточно — прямо скажи, чего не хватает.
Никогда не придумывай оплату, даты, расписание, договорённости или содержание занятий.
Пиши коротко, по делу, в стиле личного помощника. Если уместно — предложи следующее безопасное действие, но не утверждай, что оно выполнено.'''
    user = f'''УЧЕНИК: {recipient_name}\nВОПРОС АДМИНИСТРАТОРА: {question}\n\nФАКТЫ:\n{facts[:4000]}\n\nНЕДАВНЯЯ ПЕРЕПИСКА:\n{recent_messages[:2500]}'''
    return await _chat_final([
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': user},
    ], temperature=0.15, max_tokens=650)


async def rewrite_message(*, draft: str, instruction: str, recipient_type: str,
                          facts: str = '') -> str:
    system = '''Ты — Аделия, помощница преподавателя. Перепиши готовый черновик Telegram-сообщения по просьбе администратора.
Сохрани смысл и факты. Не добавляй новые суммы, даты, обещания, свободные окна или другие сведения, которых нет в ФАКТАХ или исходном черновике.
Для родителя используй вежливое обращение на «Вы». Верни только новый текст сообщения без пояснений.'''
    user = f'''ТИП ПОЛУЧАТЕЛЯ: {recipient_type}\nЧТО ИЗМЕНИТЬ: {instruction}\n\nФАКТЫ:\n{facts[:3000]}\n\nИСХОДНЫЙ ЧЕРНОВИК:\n{draft[:3500]}'''
    return await _chat_final([
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': user},
    ], temperature=0.3, max_tokens=650)


async def draft_channel_post(*, instruction: str, context: str = '') -> str:
    system = '''Ты — Аделия, помощница преподавателя. Подготовь готовый пост для Telegram-канала на русском языке.
Пиши естественно, тепло и профессионально. Не называй себя ИИ. Не придумывай даты, цены, расписание, свободные окна, результаты или обещания, которых нет во входных данных.
Если администратор дал только идею без фактов, сделай универсальный текст без выдуманных деталей.
Структура должна хорошо читаться в Telegram: короткие абзацы, при необходимости 1–4 уместных эмодзи. Обычно до 1200 символов.
Верни ТОЛЬКО текст поста без пояснений и без кавычек.'''
    user = f"ЗАДАЧА АДМИНИСТРАТОРА:\n{instruction[:2500]}\n\nДОПОЛНИТЕЛЬНЫЙ КОНТЕКСТ:\n{context[:2500]}"
    return await _chat_final([
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': user},
    ], temperature=0.45, max_tokens=900)


async def draft_broadcast(*, instruction: str, audience: str, context: str = '') -> str:
    system = '''Ты — Аделия, помощница преподавателя. Подготовь текст массового Telegram-сообщения ученикам.
Текст должен подходить всей выбранной аудитории и не выглядеть как безличный спам. Не используй персональные имена.
Не придумывай даты, цены, изменения расписания, дедлайны, ссылки или другие факты, которых нет во входных данных.
Не утверждай, что что-то уже сделано. Обычно 2–7 коротких предложений, умеренные эмодзи. Верни ТОЛЬКО текст сообщения.'''
    user = f"АУДИТОРИЯ: {audience}\nЗАДАЧА АДМИНИСТРАТОРА:\n{instruction[:2500]}\n\nКОНТЕКСТ:\n{context[:2000]}"
    return await _chat_final([
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': user},
    ], temperature=0.4, max_tokens=850)
