"""Periodic TutorBot job for tracked homework reminders and outbox delivery.

Reminder state is advanced only after the durable outbox item has actually been
delivered. Queueing alone is not considered delivery, so transient Telegram/VK
failures remain retryable without losing the reminder.
"""
from web_backend.external_homework import reminders_due
from web_backend.homework_notifications import enqueue_external_reminder
from web_backend.homework_notification_worker import process_pending


async def job(context):
    queued=0
    for item in reminders_due(limit=100):
        if enqueue_external_reminder(item):
            queued+=1
    delivery=await process_pending(context,limit=100)
    return {'reminders_queued':queued,'delivery':delivery}
