"""Web facade for TutorBot's canonical slot-change / exchange workflow."""
from __future__ import annotations
from datetime import datetime, timedelta
import database
from final_features import slot_change
from web_backend.student_booking import free_slots
ACTIVE_REQUESTS={'PENDING_ADMIN','WAITING_OCCUPANT','WAITING_FINAL_ADMIN'}

def _lesson_owned(user_id,lesson_id):
    lesson=database.get_lesson(int(lesson