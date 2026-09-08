"""TutorBot-side worker for homework notifications.

Call `process_pending(context)` from an existing Telegram job. Student delivery
uses the same cross-channel send_student() already used by lesson notifications.
Teacher Telegram delivery uses the existing admin bot context. No web request
imports or owns Telegram/VK clients.
"""
import admin
from web_backend.homework_notifications import pending, mark_delivered, mark_failed


async def process_pending(context,limit=50):
    items=pending(limit);sent=0
    for item in items:
        try:
            text=item['text'];url=item['action_url'];label=item['action_label']
            if url:text += f"\n\n{label or 'Открыть'}: {url}"
            if item['recipient_type']=='STUDENT':
                from vk_adapter.channel_delivery import send_student
                send_student(int(item['user_id']),text)
            elif item['recipient_type']=='TEACHER':
                await context.bot.send_message(chat_id=int(admin.ADMIN_ID),text=text,disable_web_page_preview=True)
            else:
                raise ValueError('unknown_recipient_type')
            mark_delivered(item['id']);sent+=1
        except Exception as exc:
            mark_failed(item['id'],repr(exc))
    return {'processed':len(items),'delivered':sent}
