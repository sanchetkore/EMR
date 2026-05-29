from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime
from app.schemas.user import User

class PatientBase(BaseModel):
    first_name: str
    last_name: str
    dob: date
    gender: str
    contact_number: str
    email: Optional[str] = None
    blood_group: Optional[str] = None
    emergency_contact: Optional[str] = None
    emergency_phone: Optional[str] = None
    address: Optional[str] = None
    is_active: Optional[int] = 1

class PatientCreate(PatientBase):
    pass

class Patient(PatientBase):
    id: int
    class Config:
        orm_mode = True

class AppointmentStatusConfigBase(BaseModel):
    name: str
    color: Optional[str] = None
    is_active: Optional[int] = 1

class AppointmentStatusConfigCreate(AppointmentStatusConfigBase):
    pass

class AppointmentStatusConfig(AppointmentStatusConfigBase):
    id: int
    class Config:
        orm_mode = True

class AppointmentBase(BaseModel):
    patient_id: int
    doctor_id: int
    appointment_time: datetime
    status: Optional[str] = "Scheduled"

class AppointmentCreate(AppointmentBase):
    pass

class Appointment(AppointmentBase):
    id: int
    patient: Optional[Patient] = None
    doctor: Optional[User] = None
    class Config:
        orm_mode = True
