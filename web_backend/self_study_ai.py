"""Language-only provider configuration; never mutates bot/work AI settings."""
import json,os
from pathlib import Path
from urllib.parse import urlsplit

CONFIG_PATH=Path(os.environ.get('ADELIA_LANGUAGE_AI_FILE','/etc/adelia-family-languages/ai.json'))


def validate(value):
 if not isinstance(value,dict):raise ValueError('invalid_language_ai_config')
 key=value.get('api_key');model=value.get('model');base=value.get('base_url')
 if not all(isinstance(s,str) and s.strip() for s in (key,model,base)):raise ValueError('invalid_language_ai_config')
 if 'ВСТАВЬ' in key.upper() or len(model)>200:raise ValueError('invalid_language_ai_config')
 url=urlsplit(base)
 if url.scheme!='https' or not url.hostname or url.username or url.password or url.query or url.fragment:raise ValueError('invalid_language_ai_config')
 return {'id':'family_language_openrouter','title':'Семейные языки · OpenRouter','type':'openrouter','kind':'openai','api_key':key.strip(),'base_url':base.rstrip('/'),'model':model.strip(),'enabled':True}


def active_provider():
 if CONFIG_PATH.exists():
  try:return validate(json.loads(CONFIG_PATH.read_text(encoding='utf-8')))
  except (OSError,ValueError,TypeError):return None
 from ai_assistant import providers
 return providers.active_provider()
