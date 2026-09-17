"""Teacher availability settings shared by web and desktop clients.

Weekly working hours define self-bookable time. Date exceptions let the teacher
close a whole day or an interval. Existing lessons are never silently moved or
deleted: affected students are notified and can either reschedule or cancel.
"""
from __future__ import annotations

from datetime import date, datetime
import re

