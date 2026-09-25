import os
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


DEFAULT_TIMEZONE = "America/Bahia"


def operational_timezone():
    return ZoneInfo(os.getenv("APP_TIMEZONE", DEFAULT_TIMEZONE))


def period_local_naive_bounds(start_date, end_date):
    """Return half-open bounds for legacy local-naive timestamps."""
    return datetime.combine(start_date, time.min), datetime.combine(end_date + timedelta(days=1), time.min)


def period_utc_naive_bounds(start_date, end_date):
    """Convert local dates to half-open UTC-naive bounds for legacy UTC columns."""
    local_tz = operational_timezone()
    start_local = datetime.combine(start_date, time.min, tzinfo=local_tz)
    end_local = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=local_tz)
    return start_local.astimezone(timezone.utc).replace(tzinfo=None), end_local.astimezone(timezone.utc).replace(tzinfo=None)


def local_period_to_utc(start_date, end_date):
    """Backward-compatible alias for UTC-naive period bounds."""
    return period_utc_naive_bounds(start_date, end_date)


def local_today():
    return datetime.now(operational_timezone()).date()
