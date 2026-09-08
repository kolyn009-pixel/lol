"""Periodic TutorBot job for tracked homework reminders and outbox delivery.

Designed to be called by the existing Telegram JobQueue. It is intentionally
small so production wiring can be reviewed separately from the web feature.
"""
from web_backend.external_homework import reminders_due, mark_reminder_sent
from web_backend.homework_notifications import enqueue_external_reminder
from web_backend.homework_notification_worker import process_pending


async def job(context):
    queued=0
    for item in reminders_due(limit=100):
        if enqueue_external_reminder(item):
            queued+=1
        # The durable outbox now owns retrying delivery; don't enqueue it again.
        mark_reminder_sent(item['homework_id'],item['user_id'])
    delivery=await process_pending(context,limit=100)
    return {'reminders_queued':queued,'delivery':delivery}
