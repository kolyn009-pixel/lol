from datetime import datetime
from . import messaging, student_history
from core import event_center

async def scheduled_messages_job(context):
    for row in messaging.due():
        errors=[]; sent=0
        for tid in messaging.target_telegram_ids(row):
            try:
                await context.bot.send_message(tid,row['text']); sent+=1
            except Exception as exc: errors.append(str(exc))
        messaging.mark_sent(row['id'], '; '.join(errors[:3]) if errors and sent==0 else None)
        if errors:
            event_center.push('SCHEDULED_MESSAGE_PARTIAL','Ошибки отложенной рассылки',f"Сообщение #{row['id']}: отправлено {sent}, ошибок {len(errors)}",priority='ATTENTION',dedupe_key=f"schedmsg:{row['id']}")

async def timeline_sync_job(context):
    try: student_history.rebuild_basic()
    except Exception as exc:
        event_center.push('TIMELINE_SYNC_ERROR','Ошибка обновления истории учеников',str(exc),priority='ATTENTION',dedupe_key='timeline_sync')
