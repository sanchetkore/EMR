from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.models.patient import Appointment
from app.schemas.patient import Appointment as AppointmentSchema, AppointmentCreate
from app.api.deps import RequirePermission

router = APIRouter()

from typing import List, Optional
from datetime import date
from sqlalchemy import cast, Date

@router.get("/", response_model=List[AppointmentSchema], dependencies=[Depends(RequirePermission("view_appointments"))])
def get_appointments(
    patient_id: Optional[int] = None,
    doctor_id: Optional[int] = None,
    appointment_date: Optional[date] = None,
    status: Optional[str] = None,
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
    return query.all()

@router.post("/", response_model=AppointmentSchema, dependencies=[Depends(RequirePermission("manage_appointments"))])
def create_appointment(appointment: AppointmentCreate, db: Session = Depends(get_db)):
    db_appointment = Appointment(**appointment.dict())
    db.add(db_appointment)
    db.commit()
    db.refresh(db_appointment)
    return db_appointment

@router.get("/{appointment_id}", response_model=AppointmentSchema, dependencies=[Depends(RequirePermission("view_appointments"))])
def get_appointment(appointment_id: int, db: Session = Depends(get_db)):
    db_appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not db_appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return db_appointment

@router.put("/{appointment_id}", response_model=AppointmentSchema, dependencies=[Depends(RequirePermission("manage_appointments"))])
def update_appointment(appointment_id: int, appointment_update: AppointmentCreate, db: Session = Depends(get_db)):
    db_appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not db_appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    
    for var, value in vars(appointment_update).items():
        setattr(db_appointment, var, value)
        
    db.commit()
    db.refresh(db_appointment)
    return db_appointment

@router.put("/{appointment_id}/status", response_model=AppointmentSchema, dependencies=[Depends(RequirePermission("manage_appointments"))])
def update_appointment_status(appointment_id: int, status: str, db: Session = Depends(get_db)):
    db_appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not db_appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    db_appointment.status = status
    db.commit()
    db.refresh(db_appointment)
    return db_appointment

@router.delete("/{appointment_id}", dependencies=[Depends(RequirePermission("manage_appointments"))])
def delete_appointment(appointment_id: int, db: Session = Depends(get_db)):
    db_appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not db_appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    db.delete(db_appointment)
    db.commit()
    return {"detail": "Appointment deleted successfully"}
