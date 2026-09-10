import os
import asyncio

from datetime import (
    datetime,
    timedelta,
    date,
)

from zoneinfo import ZoneInfo

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    BotCommand,
    BotCommandScopeDefault,
    BotCommandScopeChat,
)

from telegram.error import NetworkError, TimedOut, BadRequest

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    TypeHandler,
    ApplicationHandlerStop,
    filters,
)

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import database
import admin
import payments
import students_admin
import schedule_admin
import channel_admin

from core import admin_roles
from core import audit_log as core_audit_log
from core import backup_manager as core_backup_manager
from core import event_center as core_event_center
from core import minute_balance
from core import financial_ledger as core_financial_ledger
from core import maintenance as core_maintenance
from core import teacher_tasks
from core import test_lab as core_test_lab
from core import stage1_admin as core_stage1_admin
from core import user_timezone
from learning import schema as learning_schema
from learning import curriculum as learning_curriculum
from handlers import learning_handlers
from learning import formula_study
from learning import homework_flow
from automation import schema as automation_schema
from automation import notifications as automation_notifications
from automation import schedule_tools as automation_schedule_tools
from automation import jobs as automation_jobs
from handlers import stage3_handlers
from handlers import stage3_role_ux
from handlers import stage3_admin_extras
from handlers import minute_admin_handlers
from handlers import admin_inbox_handlers
from handlers import musthave_admin
from handlers import musthave_jobs
from handlers import task_admin
from handlers import ai_provider_admin
from handlers import adelia_content
from handlers import student_message_handlers
from handlers import message_center_handlers
from handlers import global_home_handlers
from handlers import admin_student_router
from handlers import timezone_handlers
from final_features import schema as final_schema
from final_features import curriculum_full as final_curriculum
from final_features import handlers_wrapper as final_handlers
from final_features import jobs as final_jobs
from crm_plus import schema as crm_schema
from crm_plus import handlers as crm_handlers
from crm_plus import jobs as crm_jobs
from final_features import ledger as final_minute_ledger
from ux_final import schema as ux_schema
from ux_final import handlers as ux_handlers


# ============================================================
# НАСТРОЙКИ
# ============================================================

BOT_TOKEN = os.getenv('BOT_TOKEN', '').strip()

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

TOKEN_FILE = os.path.join(
    BASE_DIR,
    "token.json"
)

SCOPES = [
    "https://www.googleapis.com/auth/calendar"
]

CALENDAR_ID = "primary"

TIMEZONE_NAME = "Europe/Samara"

TIMEZONE = ZoneInfo(
    TIMEZONE_NAME
)

def apply_bot_timezone(name=None):
    """Apply TutorBot timezone to all runtime scheduling and local-time helpers."""
    global TIMEZONE_NAME, TIMEZONE
    name = name or database.get_setting("bot_timezone", "Europe/Samara") or "Europe/Samara"
    try:
        tz = ZoneInfo(name)
    except Exception:
        name = "Europe/Samara"
        tz = ZoneInfo(name)
    TIMEZONE_NAME = name
    TIMEZONE = tz
    try:
        import os as _os, time as _time
        _os.environ["TZ"] = name
        if hasattr(_time, "tzset"):
            _time.tzset()
    except Exception:
        pass
