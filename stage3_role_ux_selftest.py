import pathlib, re
root=pathlib.Path(__file__).resolve().parent
bot=(root/'bot.py').read_text(encoding='utf-8')
ux=(root/'handlers/stage3_role_ux.py').read_text(encoding='utf-8')
checks=['uxs3_study','uxs3_repeat','uxs3_solutions','uxp3_summary','uxp3_report','uxp3_attention','uxp3_homework','stage3_role_ux.handlers()']
for x in checks:
    if x not in bot+ux: raise RuntimeError('missing '+x)
if 'callback_data="fh_study"' in bot: raise RuntimeError('old student study callback still active in main menu')
print('STAGE3 ROLE UX SELFTEST: OK')
