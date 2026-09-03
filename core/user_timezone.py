from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import database

MOSCOW_ZONE = "Europe/Moscow"
MOSCOW = ZoneInfo(MOSCOW_ZONE)

# Human-facing presets. The UI intentionally speaks in offsets from Moscow.
PRESETS = [
    ("🇷🇺 Москва", 0, "Europe/Moscow"),
    ("🇷🇺 Самара", 1, "Europe/Samara"),
    ("🇷🇺 Екатеринбург", 2, "Asia/Yekaterinburg"),
    ("🇷🇺 Омск", 3, "Asia/Omsk"),
    ("🇷🇺 Красноярск", 4, "Asia/Krasnoyarsk"),
    ("🇷🇺 Иркутск", 5, "Asia/Irkutsk"),
]


def msk_label(offset: int | str | None) -> str:
    try:
        value = int(offset or 0)
    except Exception:
        value = 0
    if value == 0:
        return "МСК"
    return f"МСК {value:+d}"


def fixed_zone_name_from_msk_offset(offset: int) -> str:
    """Return an IANA fixed-offset zone matching Moscow + offset.

    Etc/GMT signs are reversed by the IANA convention.
    """
    utc_hours = 3 + int(offset)
    if utc_hours == 0:
        return "UTC"
    if utc_hours > 0:
        return f"Etc/GMT-{utc_hours}"
    return f"Etc/GMT+{abs(utc_hours)}"


def tzinfo_from_pref(pref) -> timezone | ZoneInfo:
    if pref:
        zone_name = pref.get("zone_name") if hasattr(pref, "get") else pref["zone_name"]
        if zone_name:
            try:
                return ZoneInfo(str(zone_name))
            except Exception:
                pass
        try:
            offset = int(pref.get("msk_offset") if hasattr(pref, "get") else pref["msk_offset"])
            return timezone(timedelta(hours=3 + offset))
        except Exception:
            pass
    return MOSCOW


def preference(telegram_id: int):
    try:
        return database.get_user_timezone(int(telegram_id))
    except Exception:
        return None


def configured(telegram_id: int) -> bool:
    pref = preference(telegram_id)
    return bool(pref and int(pref["configured"] or 0))


def user_tz(telegram_id: int, fallback_zone: str | None = None):
    pref = preference(telegram_id)
    if pref and int(pref["configured"] or 0):
        return tzinfo_from_pref(pref)
    if fallback_zone:
        try:
            return ZoneInfo(str(fallback_zone))
        except Exception:
            pass
    return MOSCOW


def user_label(telegram_id: int, fallback_zone: str | None = None) -> str:
    pref = preference(telegram_id)
    if pref and int(pref["configured"] or 0):
        return msk_label(pref["msk_offset"])
    if fallback_zone:
        return zone_label(fallback_zone)
    return "МСК"


def zone_label(zone_name: str) -> str:
    try:
        now = datetime.now(ZoneInfo(zone_name))
        msk_now = now.astimezone(MOSCOW)
        # Whole-hour zones are intentionally supported in the UX.
        diff = int(round((now.utcoffset() - msk_now.utcoffset()).total_seconds() / 3600))
        return msk_label(diff)
    except Exception:
        return "МСК"


def parse_datetime(value, source_zone: str = "Europe/Samara") -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value))
        except Exception:
            return None
    if dt.tzinfo is None:
        try:
            dt = dt.replace(tzinfo=ZoneInfo(source_zone))
        except Exception:
            dt = dt.replace(tzinfo=MOSCOW)
    return dt


def convert_for_user(value, telegram_id: int, source_zone: str = "Europe/Samara") -> datetime | None:
    dt = parse_datetime(value, source_zone)
    if dt is None:
        return None
    return dt.astimezone(user_tz(telegram_id, source_zone))


def format_for_user(value, telegram_id: int, source_zone: str = "Europe/Samara", fmt: str = "%d.%m.%Y %H:%M", with_zone: bool = False) -> str:
    dt = convert_for_user(value, telegram_id, source_zone)
    if dt is None:
        return "—"
    text = dt.strftime(fmt)
    if with_zone:
        text += f" · {user_label(telegram_id, source_zone)}"
    return text


def format_time_for_user(value, telegram_id: int, source_zone: str = "Europe/Samara", with_zone: bool = False) -> str:
    return format_for_user(value, telegram_id, source_zone, "%H:%M", with_zone)


def format_day_time_for_user(value, telegram_id: int, source_zone: str = "Europe/Samara", with_zone: bool = True) -> str:
    return format_for_user(value, telegram_id, source_zone, "%d.%m.%Y %H:%M", with_zone)
