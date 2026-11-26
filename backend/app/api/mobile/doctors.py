from app.api.mobile.clock import clinic_now
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from datetime import datetime, date as calendar_date, time, timedelta
from app.models.patient import Appointment
from app.services.clinic_closures import closure_reason
from app.api.mobile.deps import get_current_patient
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.user import User, Role
from app.models.patient import AppointmentTypeConfig
from app.models.settings import SystemSetting

router = APIRouter(prefix="/doctors", tags=["mobile-doctors"], dependencies=[Depends(get_current_patient)])

def configured_slot_starts(db: Session, target: calendar_date) -> list[datetime]:
    keys = ("start_time", "end_time", "slot_duration_minutes")
    settings = dict(db.query(SystemSetting.key, SystemSetting.value).filter(SystemSetting.key.in_(keys)).all())
    try:
        start = datetime.combine(target, datetime.strptime(settings["start_time"], "%H:%M").time())
        end = datetime.combine(target, datetime.strptime(settings["end_time"], "%H:%M").time())
        minutes = int(settings["slot_duration_minutes"])
    except (KeyError, TypeError, ValueError):
        return []
    if not 1 <= minutes <= 1440:
        return []
    span_minutes = (end - start) // timedelta(minutes=1)
    return [start + timedelta(minutes=offset) for offset in range(0, span_minutes + 1, minutes)]


def available_doctor_slots(db: Session, doctor_id: int, target: calendar_date) -> list[str]:
    now = clinic_now()
    if target < now.date() or closure_reason(db, target):
        return []
    existing = db.query(Appointment.appointment_time).filter(
        Appointment.doctor_id == doctor_id,
        Appointment.appointment_time >= datetime.combine(target, time.min),
        Appointment.appointment_time <= datetime.combine(target, time.max),
        Appointment.status != "Cancelled",
    ).all()
    occupied = {start.replace(second=0, microsecond=0) for (start,) in existing}
    return [start.strftime("%I:%M %p") for start in configured_slot_starts(db, target)
            if start > now and start not in occupied]

def doctor_metadata(rate, slots_csv):
    return {"specialty": "Clinic physician", "credentials": "", "bio": "",
        "experienceYears": 0, "rating": 0, "reviewCount": 0,
        "consultationFeeCents": rate, "clinicRoom": "Confirm at reception",
        "avatarKey": "", "workingDaysCsv": "Mon, Tue, Wed, Thu, Fri, Sat",
        "availableSlotsCsv": slots_csv}

@router.get("/")
def get_doctors(db: Session = Depends(get_db)):
    doctor_users = db.query(User).join(Role).filter(Role.name == "Doctor", User.is_active == True).all()

    # Get consultation rates if configured
    apt_type = db.query(AppointmentTypeConfig).filter(AppointmentTypeConfig.is_active == 1).first()
    default_rate_cents = round((apt_type.rate or 0) * 100) if apt_type else 0
    slots_csv = ", ".join(start.strftime("%I:%M %p") for start in configured_slot_starts(db, clinic_now().date()))

    results = []
    for doc in doctor_users:
        meta = doctor_metadata(default_rate_cents, slots_csv)

        results.append({
            "id": str(doc.id),
            "name": f"Dr. {doc.username.capitalize()}",
            "specialty": meta["specialty"],
            "credentials": meta["credentials"],
            "bio": meta["bio"],
            "experienceYears": meta["experienceYears"],
            "rating": meta["rating"],
            "reviewCount": meta["reviewCount"],
            "consultationFeeCents": meta["consultationFeeCents"],
            "clinicRoom": meta["clinicRoom"],
            "avatarKey": meta["avatarKey"],
            "workingDaysCsv": meta["workingDaysCsv"],
            "availableSlotsCsv": meta["availableSlotsCsv"]
        })

    return results

@router.get("/{doctor_id}/slots")
def get_doctor_slots(doctor_id: int, date: Optional[str] = Query(None), db: Session = Depends(get_db)):
    doctor = db.query(User.id).join(Role).filter(User.id == doctor_id, Role.name == "Doctor", User.is_active == True).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
    try:
        target = calendar_date.fromisoformat(date) if date else clinic_now().date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid appointment date")
    return {"doctorId": str(doctor_id), "date": target.isoformat(), "slots": available_doctor_slots(db, doctor_id, target)}
