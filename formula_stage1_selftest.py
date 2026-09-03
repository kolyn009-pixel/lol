from pathlib import Path
from formula_library import FORMULA_LIBRARY

src = Path('learning/formula_study.py').read_text()
assert 10 in FORMULA_LIBRARY and 'PHYSICS' in FORMULA_LIBRARY[10]
assert 8 in FORMULA_LIBRARY and 'CHEMISTRY' in FORMULA_LIBRARY[8]
for token in ['formula_favorites','formula_recent','formula_quiz_stats','🔎 Найти формулу','⭐ Избранные','🧠 Проверить себя','fh_search','fh_topic|']:
    assert token in src, token
assert '📚 Моя учёба' in Path('bot.py').read_text()
assert 'formula_study.initialize()' in Path('bot.py').read_text()
print('FORMULA STAGE1 SELFTEST: OK')
