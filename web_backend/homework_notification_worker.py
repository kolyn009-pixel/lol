"""TutorBot-side worker for durable homework notifications."""
import admin
from web_backend.homework_notifications import pending,mark_delivered,mark_failed


def _after_delivery(item):
    """Advance source state only after transport success."""
    if item.get('event_type')=='EXTERNAL_HOMEWORK_REMINDER':
        from web_backend.external_homework import mark_reminder_sent
        import json
        try:payload=json.loads(item.get('payload_json') or '{}')
        except Exception:payload={}
        homework_id=payload.get('homework_id')
        user_id=item.get('user_id')
        if homework_id is not None and user_id is not None:
            mark_reminder_sent(int(homework_id),int(user_id))


async def process_pending(context,limit=50):
    items=pending(limit);sent=0
    for item in items:
        try:
            text=item['text'];url=item['action_url'];label=item['action_label']
            if url:text+=f"\n\n{label or 'Открыть'}: {url}"
            if item['recipient_type']=='STUDENT':
                from vk_adapter.channel_delivery import send_student
                send_student(int(item['user_id']),text)
            elif item['recipient_type']=='TEACHER':
                await context.bot.send_message(chat_id=int(admin.ADMIN_ID),text=text,disable_web_page_preview=True)
            else:raise ValueError('unknown_recipient_type')
            # Source acknowledgement precedes outbox completion. If it fails, the
            # outbox remains pending and can retry instead of silently losing state.
            _after_delivery(item)
            mark_delivered(item['id']);sent+=1
        except Exception as exc:
            mark_failed(item['id'],repr(exc))
    return {'processed':len(items),'delivered':sent}
