"""Mobile booking dates follow the clinic's wall clock, independent of server TZ."""
import os
from datetime import datetime
from zoneinfo import ZoneInfo


def clinic_timezone():
    return ZoneInfo(os.getenv('CLINIC_TIMEZONE', 'Asia/Kolkata'))


def clinic_now():
    return datetime.now(clinic_timezone()).replace(tzinfo=None)
