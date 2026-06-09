from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from app.core.websocket import manager
from app.api.queue import get_live_queue
from typing import List
from app.core.database import get_db
from app.models.patient import Appointment, AppointmentStatusConfig, AppointmentTypeConfig, Patient
from app.schemas.patient import Appointment as AppointmentSchema, AppointmentCreate, AppointmentStatusConfig as AppointmentStatusSchema, AppointmentStatusConfigCreate, AppointmentTypeConfig as AppointmentTypeSchema, AppointmentTypeConfigCreate
from app.api.deps import RequirePermission

router = APIRouter()

from typing import List, Optional
from datetime import date, datetime, timedelta, timezone
from sqlalchemy import cast, Date, or_

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
    status: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    query = db.query(Appointment)
    if patient_id:
        query = query.filter(Appointment.patient_id == patient_id)
    if doctor_id:
        query = query.filter(Appointment.doctor_id == doctor_id)
    if appointment_date:
        query = query.filter(cast(Appointment.appointment_time, Date) == appointment_date)
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
    return query.offset(skip).limit(limit).all()

@router.post("/", response_model=AppointmentSchema, dependencies=[Depends(RequirePermission("manage_appointments"))])
def create_appointment(appointment: AppointmentCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    # Auto-generate token_number based on the day of the appointment
    apt_date = appointment.appointment_time.date()
    
    # We construct datetimes for start and end of that specific day
    start_of_day = datetime.combine(apt_date, datetime.min.time())
    end_of_day = datetime.combine(apt_date, datetime.max.time())
    
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

    prescription_data = appointment.dict()
    prescription_data['token_number'] = new_token
    
    db_appointment = Appointment(**prescription_data)
    db.add(db_appointment)
    db.commit()
    db.refresh(db_appointment)
    
    # Broadcast new queue to TVs
    payload = get_live_queue(db)
    background_tasks.add_task(manager.broadcast, payload)
    
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
