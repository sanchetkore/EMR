import re
from datetime import date
from typing import Annotated

from pydantic import BaseModel, Field, model_validator
from sqlalchemy.exc import IntegrityError

from app.models.mobile import MobileBloodPickup
from app.models.settings import SystemSetting

SETTING_KEY = "home_pickup_slots"


class PickupSlot(BaseModel):
    start: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    duration: int = Field(ge=5, le=720)
    capacity: int = Field(ge=1, le=1000)

    @property
    def start_minutes(self):
        hour, minute = map(int, self.start.split(":"))
        return hour * 60 + minute

    @property
    def end_minutes(self):
        return self.start_minutes + self.duration

    @property
    def label(self):
        def display(minutes):
            hour, minute = divmod(minutes, 60)
            return f"{hour % 12 or 12:02}:{minute:02} {'AM' if hour < 12 or hour == 24 else 'PM'}"
        return f"{display(self.start_minutes)} – {display(self.end_minutes)}"


class PickupSchedule(BaseModel):
    slots: Annotated[list[PickupSlot], Field(max_length=48)]

    @model_validator(mode="after")
    def validate_schedule(self):
        self.slots.sort(key=lambda slot: slot.start_minutes)
        if any(slot.end_minutes > 1440 for slot in self.slots):
            raise ValueError("Collection slots must finish by midnight.")
        if any(first.end_minutes > second.start_minutes for first, second in zip(self.slots, self.slots[1:])):
            raise ValueError("Collection slots cannot overlap.")
        return self


def pickup_schedule(db, *, lock=False):
    query = db.query(SystemSetting).filter(SystemSetting.key == SETTING_KEY)
    default = PickupSchedule(slots=[PickupSlot(start=start, duration=60, capacity=1)
                                    for start in ("06:30", "07:30", "08:30", "09:30")])
    if lock:
        if not query.update({SystemSetting.value: SystemSetting.value}, synchronize_session=False):
            try:
                with db.begin_nested():
                    db.add(SystemSetting(key=SETTING_KEY, value=default.model_dump_json()))
                    db.flush()
            except IntegrityError:
                query.update({SystemSetting.value: SystemSetting.value}, synchronize_session=False)
    row = query.populate_existing().first()
    return row, PickupSchedule.model_validate_json(row.value) if row else default


def booked_windows(db, day: date):
    rows = db.query(MobileBloodPickup.time_window).filter(
        MobileBloodPickup.pickup_date_iso == day.isoformat(),
        MobileBloodPickup.status != "CANCELLED",
    )
    windows = []
    for (label,) in rows:
        time_parts = re.findall(r"(\d{1,2}):(\d{2})\s*(AM|PM)", label, re.IGNORECASE)
        if len(time_parts) == 2:
            start, end = (int(hour) % 12 * 60 + int(minute) + (720 if part.upper() == "PM" else 0)
                          for hour, minute, part in time_parts)
            windows.append((start, end or 1440))
    return windows


def remaining_collections(slot: PickupSlot, windows):
    occupied = sum(start < slot.end_minutes and slot.start_minutes < end for start, end in windows)
    return max(0, slot.capacity - occupied)
