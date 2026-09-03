from ai_assistant.client import _sanitize_final_text, _looks_like_reasoning, _looks_like_placeholder

sample = '''Here's a thinking process:\n1. Analyze User Input\n2. Constraints\nFinal answer:\nПривет! Пока занятий нет 🙂'''
clean = _sanitize_final_text(sample)
assert clean == 'Привет! Пока занятий нет 🙂', clean
assert not _looks_like_reasoning(clean)
assert _looks_like_placeholder('ВСТАВЬ_СЮДА_ТВОЙ_OPENROUTER_KEY')
assert not _looks_like_placeholder('sk-or-v1-abc123')

marked = 'noise\n<<<FINAL>>>Готовый текст<<<END>>>\nmore noise'
assert _sanitize_final_text(marked) == 'Готовый текст'
print('AI SELFTEST OK')
