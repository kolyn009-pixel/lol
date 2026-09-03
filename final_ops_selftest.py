from pathlib import Path
import tempfile, sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from ai_assistant import providers

with tempfile.TemporaryDirectory() as d:
    providers.CONFIG_PATH=Path(d)/'providers.json'
    pid=providers.save_provider('custom','secret-test-key-123',model='demo-model',base_url='https://example.invalid/v1')
    assert providers.get_provider(pid)['model']=='demo-model'
    providers.set_active(pid)
    assert providers.load_config()['active']==pid
    assert 'secret-test-key-123' not in str(providers.provider_list())
    assert oct(providers.CONFIG_PATH.stat().st_mode & 0o777)=='0o600'
print('AI PROVIDER CONFIG SELFTEST: OK')

text=(ROOT/'core/teacher_tasks.py').read_text(encoding='utf-8')
for token in ['teacher_tasks','unpaid:','no_next:','homework:']:
    assert token in text
print('TEACHER TASKS SELFTEST: OK')
