"""Provider acknowledgement handling; ambiguous network failures never auto-retry."""
import json,os
from urllib.error import HTTPError,URLError
from urllib.parse import urlencode
from urllib.request import Request,urlopen

class Retryable(Exception):pass
class Permanent(Exception):pass
class Uncertain(Exception):pass

def _post(url,values):
 try:
  with urlopen(Request(url,data=urlencode(values).encode(),headers={'Content-Type':'application/x-www-form-urlencoded'}),timeout=20) as response:return json.loads(response.read())
 except HTTPError as exc:
  if exc.code==429:raise Retryable('provider_rate_limit') from None
  if exc.code in {400,401,403,404}:raise Permanent('provider_rejected_'+str(exc.code)) from None
  raise Uncertain('provider_response_unknown') from None
 except (OSError,ValueError,URLError):raise Uncertain('network_result_unknown') from None

def send(channel,recipient,text,event_id):
 if channel=='TELEGRAM':
  token=os.getenv('BOT_TOKEN','').strip()
  if not token:raise Permanent('telegram_token_missing')
  result=_post('https://api.telegram.org/bot'+token+'/sendMessage',{'chat_id':int(recipient),'text':text})
  if not result.get('ok'):raise Permanent('telegram_rejected')
  if not isinstance(result.get('result'),dict) or not result['result'].get('message_id'):raise Uncertain('telegram_ack_missing')
  return str(result['result']['message_id'])
 if channel!='VK':raise Permanent('unsupported_channel')
 token=os.getenv('VK_TOKEN','').strip()
 if not token:raise Permanent('vk_token_missing')
 if not 0<int(event_id)<2_000_000_000:raise Permanent('vk_event_id_out_of_range')
 result=_post('https://api.vk.com/method/messages.send',{'peer_id':int(recipient),'message':text,'random_id':int(event_id),'access_token':token,'v':os.getenv('VK_API_VERSION','5.199')})
 if 'error' in result:
  code=(result.get('error') or {}).get('error_code')
  if code in {6,9}:raise Retryable('vk_rate_limit')
  raise Permanent('vk_rejected_'+str(code))
 if not result.get('response'):raise Uncertain('vk_ack_missing')
 return str(result['response'])
