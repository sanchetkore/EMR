from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session, joinedload
from app.core.websocket import manager
from app.api.queue import get_live_queue
from typing import List
from app.core.database import get_db
from app.models.patient import Appointment, AppointmentStatusConfig, AppointmentTypeConfig, Patient
from app.schemas.patient import Appointment as AppointmentSchema, AppointmentCreate, AppointmentStatusConfig as AppointmentStatusSchema, AppointmentStatusConfigCreate, AppointmentTypeConfig as AppointmentTypeSchema, AppointmentTypeConfigCreate
from app.api.deps import RequirePermission
from app.models.encounter import Encounter

router = APIRouter()

@router.post("/{appointment_id}/start", response_model=AppointmentSchema)
def start_consultation(appointment_id: int, background_tasks: BackgroundTasks,
                       db: Session = Depends(get_db),
                       clinician=Depends(RequirePermission("manage_clinical"))):
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appointment.doctor_id != clinician.id:
        raise HTTPException(status_code=403, detail="Only the assigned clinician can start this consultation")
    if appointment.status in ("Completed", "Cancelled", "No Show"):
        raise HTTPException(status_code=409, detail="This appointment is closed")
    appointment.status = "Ongoing"
    db.commit()
    db.refresh(appointment)
    background_tasks.add_task(manager.broadcast, get_live_queue(db))
    return appointment

from typing import List, Optional
from datetime import date, datetime, timedelta, timezone
from sqlalchemy import cast, Date, or_, func

@router.get("/types", response_model=List[AppointmentTypeSchema], dependencies=[Depends(RequirePermission("view_appointments"))])
def get_appointment_types(db: Session = Depends(get_db)):
    return db.query(AppointmentTypeConfig).filter(AppointmentTypeConfig.is_active == 1).all()

@router.post("/types", response_model=AppointmentTypeSchema, dependencies=[Depends(RequirePermission("manage_appointments"))])
def create_appointment_type(config: AppointmentTypeConfigCreate, db: Session = Depends(get_db)):
    db_config = AppointmentTypeConfig(**config.dict())
    db.add(db_config)
    db.commit()
    db.refresh(db_config)
    return db_config

@router.get("/statuses", response_model=List[AppointmentStatusSchema], dependencies=[Depends(RequirePermission("view_appointments"))])
def get_appointment_statuses(db: Session = Depends(get_db)):
    return db.query(AppointmentStatusConfig).filter(AppointmentStatusConfig.is_active == 1).all()

@router.post("/statuses", response_model=AppointmentStatusSchema, dependencies=[Depends(RequirePermission("manage_appointments"))])
def create_appointment_status(status: AppointmentStatusConfigCreate, db: Session = Depends(get_db)):
    db_status = AppointmentStatusConfig(**status.dict())
    db.add(db_status)
    db.commit()
    db.refresh(db_status)
    return db_status

@router.get("/", response_model=List[AppointmentSchema], dependencies=[Depends(RequirePermission("view_appointments"))])
def get_appointments(
    patient_id: Optional[int] = None,
    doctor_id: Optional[int] = None,
    appointment_date: Optional[date] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 500,
    db: Session = Depends(get_db)
):
    query = db.query(Appointment)
    if patient_id:
        query = query.filter(Appointment.patient_id == patient_id)
    if doctor_id:
        query = query.filter(Appointment.doctor_id == doctor_id)
    if start_date and end_date:
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())
        query = query.filter(Appointment.appointment_time >= start_dt, Appointment.appointment_time <= end_dt)
    elif appointment_date:
        start_of_day = datetime.combine(appointment_date, datetime.min.time())
        end_of_day = datetime.combine(appointment_date, datetime.max.time())
        query = query.filter(Appointment.appointment_time >= start_of_day, Appointment.appointment_time <= end_of_day)
    if status:
        query = query.filter(Appointment.status == status)

    if search:
        query = query.join(Patient).filter(
            or_(
                Patient.first_name.ilike(f"%{search}%"),
                Patient.last_name.ilike(f"%{search}%"),
                Patient.contact_number.ilike(f"%{search}%"),
                Appointment.status.ilike(f"%{search}%")
            )
        )

    query = query.order_by(Appointment.appointment_time.asc())
    appointments = query.options(
        joinedload(Appointment.patient),
        joinedload(Appointment.doctor),
        joinedload(Appointment.appointment_type)
    ).offset(skip).limit(limit).all()

    if appointments:
        latest = db.query(Encounter).filter(Encounter.appointment_id.in_([a.id for a in appointments])).order_by(Encounter.id.desc()).all()
        by_appointment = {}
        for encounter in latest:
            by_appointment.setdefault(encounter.appointment_id, encounter)
        for appointment in appointments:
            encounter = by_appointment.get(appointment.id)
            appointment.encounter_id = encounter.id if encounter else None
            appointment.encounter_status = encounter.status if encounter else None
        patient_ids = list(set(appt.patient_id for appt in appointments))
        min_time = min(appt.appointment_time for appt in appointments)

        last_visit_query = db.query(
            Appointment.patient_id,
            func.max(Appointment.appointment_time).label('last_visit')
        ).filter(
            Appointment.patient_id.in_(patient_ids),
            Appointment.status.notin_(["Cancelled", "No Show", "no show"]),
            Appointment.appointment_time < min_time
        ).group_by(Appointment.patient_id).all()

        last_visits_dict = {row.patient_id: row.last_visit for row in last_visit_query}

        for appt in appointments:
            appt.last_visit_date = last_visits_dict.get(appt.patient_id)

    return appointments

@router.post("/", response_model=AppointmentSchema, dependencies=[Depends(RequirePermission("manage_appointments"))])
def create_appointment(appointment: AppointmentCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    from app.services.clinic_closures import check_booking_day
    check_booking_day(db, appointment.appointment_time.date())
    # Auto-generate token_number based on the day of the appointment
    apt_date = appointment.appointment_time.date()

    # We construct datetimes for start and end of that specific day
    start_of_day = datetime.combine(apt_date, datetime.min.time())
    end_of_day = datetime.combine(apt_date, datetime.max.time())

    # Allow separate consultations on the same day while rejecting an
    # accidental duplicate booking for the same doctor and time.
    requested_minute = appointment.appointment_time.replace(second=0, microsecond=0)
    existing_apt = db.query(Appointment).filter(
        Appointment.patient_id == appointment.patient_id,
        Appointment.doctor_id == appointment.doctor_id,
        Appointment.appointment_time >= requested_minute,
        Appointment.appointment_time < requested_minute + timedelta(minutes=1),
        Appointment.status != "Cancelled"
    ).first()

    if existing_apt:
        raise HTTPException(status_code=409, detail="This patient already has an appointment with this doctor at this time.")

    # Find the max token number for that day
    latest_apt = db.query(Appointment).filter(
        Appointment.appointment_time >= start_of_day,
        Appointment.appointment_time <= end_of_day,
        Appointment.token_number != None
    ).order_by(Appointment.token_number.desc()).first()

    if latest_apt and latest_apt.token_number:
        try:
            next_num = int(latest_apt.token_number) + 1
            new_token = f"{next_num:03d}"
        except ValueError:
            new_token = "001"
    else:
        new_token = "001"

    prescription_data = appointment.model_dump()
    prescription_data['token_number'] = new_token

    db_appointment = Appointment(**prescription_data)
    db.add(db_appointment)
    db.commit()
    db.refresh(db_appointment)

    # Broadcast new queue to TVs
    payload = get_live_queue(db)
    background_tasks.add_task(manager.broadcast, payload)

    # Send WhatsApp/SMS notifications
    from app.services.whatsapp_service import send_appointment_whatsapp
    from app.services.sms_service import send_appointment_sms
    background_tasks.add_task(send_appointment_whatsapp, db_appointment.patient_id, db_appointment.doctor_id, db_appointment.appointment_time)
    background_tasks.add_task(send_appointment_sms, db_appointment.patient_id, db_appointment.doctor_id, db_appointment.appointment_time)

    return db_appointment

@router.get("/{appointment_id}", response_model=AppointmentSchema, dependencies=[Depends(RequirePermission("view_appointments"))])
def get_appointment(appointment_id: int, db: Session = Depends(get_db)):
    db_appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not db_appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return db_appointment

@router.put("/{appointment_id}", response_model=AppointmentSchema, dependencies=[Depends(RequirePermission("manage_appointments"))])
def update_appointment(appointment_id: int, appointment_update: AppointmentCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    db_appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not db_appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appointment_update.appointment_time != db_appointment.appointment_time and appointment_update.status not in ['Cancelled', 'No Show']:
        from app.services.clinic_closures import check_booking_day
        check_booking_day(db, appointment_update.appointment_time.date())

    for var, value in vars(appointment_update).items():
        setattr(db_appointment, var, value)

    db.commit()
    db.refresh(db_appointment)

    # Broadcast new queue to TVs
    payload = get_live_queue(db)
    background_tasks.add_task(manager.broadcast, payload)

    return db_appointment

@router.put("/{appointment_id}/status", response_model=AppointmentSchema, dependencies=[Depends(RequirePermission("manage_appointments"))])
def update_appointment_status(appointment_id: int, status: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    db_appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not db_appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    db_appointment.status = status
    db.commit()
    db.refresh(db_appointment)

    # Broadcast new queue to TVs
    payload = get_live_queue(db)
    background_tasks.add_task(manager.broadcast, payload)

    return db_appointment

@router.delete("/{appointment_id}", dependencies=[Depends(RequirePermission("manage_appointments"))])
def delete_appointment(appointment_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    db_appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not db_appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    db.delete(db_appointment)
    db.commit()

    # Broadcast new queue to TVs
    payload = get_live_queue(db)
    background_tasks.add_task(manager.broadcast, payload)

    return {"detail": "Appointment deleted successfully"}
