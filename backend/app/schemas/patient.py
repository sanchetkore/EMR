from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime
from app.schemas.user import User, UserBasic

class PatientBase(BaseModel):
    first_name: str
    last_name: str
    dob: date
    gender: str
    language: Optional[str] = None
    opd_number: Optional[str] = None
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

class AppointmentTypeConfigBase(BaseModel):
    name: str
    rate: float = 0.0
    is_active: Optional[int] = 1

class AppointmentTypeConfigCreate(AppointmentTypeConfigBase):
    pass

class AppointmentTypeConfig(AppointmentTypeConfigBase):
    id: int
    class Config:
        orm_mode = True

class AppointmentBase(BaseModel):
    patient_id: int
    doctor_id: int
    appointment_type_id: Optional[int] = None
    appointment_time: datetime
    status: Optional[str] = "Scheduled"
    token_number: Optional[str] = None

class AppointmentCreate(AppointmentBase):
    pass

class Appointment(AppointmentBase):
    id: int
    patient: Optional[Patient] = None
    doctor: Optional[UserBasic] = None
    appointment_type: Optional[AppointmentTypeConfig] = None
    class Config:
        orm_mode = True
