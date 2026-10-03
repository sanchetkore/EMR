from datetime import date
from typing import Annotated
from pydantic import BaseModel, Field
from fastapi import HTTPException
from app.models.settings import SystemSetting

SETTING_KEY = 'clinic_closures'

class Holiday(BaseModel):
    date: date
    name: str = Field(min_length=1, max_length=120)

class ClinicClosures(BaseModel):
    # Same numbering as the browser: Sunday=0, Saturday=6.
    weekly_days_off: list[Annotated[int, Field(ge=0, le=6)]] = Field(default_factory=list)
    holidays: list[Holiday] = Field(default_factory=list)

def get_closures(db):
    row = db.query(SystemSetting).filter(SystemSetting.key == SETTING_KEY).first()
    return ClinicClosures.model_validate_json(row.value) if row else ClinicClosures()

def closure_reason(db, day):
    closures = get_closures(db)
    for holiday in closures.holidays:
        if holiday.date == day:
            return holiday.name
    if (day.weekday() + 1) % 7 in closures.weekly_days_off:
        return 'Weekly holiday'
    return None

def check_booking_day(db, day):
    reason = closure_reason(db, day)
    if reason:
        raise HTTPException(409, f'Clinic closed on {day.isoformat()}: {reason}. Choose another date.')
