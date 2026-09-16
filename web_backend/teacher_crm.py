"""Teacher CRM read models and safe student profile mutations."""
from __future__ import annotations
from datetime import datetime, timedelta
from database import connect, get_user, now_iso
import education_profile
from core import minute_balance
from web_backend import monthly_allowance
RATE_FIELDS={"ege_physics_rate","oge_physics_rate","oge_chem