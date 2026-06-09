from sqlalchemy import Column, Integer, String, Date, Text, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base

class Patient(Base):
    __tablename__ = "patients"
    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, index=True)
    last_name = Column(String, index=True)
    dob = Column(Date)
    gender = Column(String)
    language = Column(String, nullable=True)
    opd_number = Column(String, nullable=True)
    contact_number = Column(String)
    email = Column(String, unique=True, index=True, nullable=True)
    blood_group = Column(String, nullable=True)
    emergency_contact = Column(String, nullable=True)
    emergency_phone = Column(String, nullable=True)
    address = Column(Text, nullable=True)
    is_active = Column(Integer, default=1) # 1 active, 0 inactive
    
    appointments = relationship("Appointment", back_populates="patient")
    ai_summaries = relationship("PatientAISummary", back_populates="patient")

class AppointmentTypeConfig(Base):
    __tablename__ = "appointment_types"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    rate = Column(Float, default=0.0)
    is_active = Column(Integer, default=1) # 1 active, 0 inactive

class AppointmentStatusConfig(Base):
    __tablename__ = "appointment_statuses"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    color = Column(String, nullable=True) # Optional hex color for UI
    is_active = Column(Integer, default=1) # 1 active, 0 inactive

class Appointment(Base):
    __tablename__ = "appointments"
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), index=True)
    doctor_id = Column(Integer, ForeignKey("users.id"), index=True) # user with doctor role
    appointment_type_id = Column(Integer, ForeignKey("appointment_types.id"), nullable=True, index=True)
    appointment_time = Column(DateTime, default=datetime.utcnow, index=True)
    status = Column(String, default="Scheduled") # Scheduled, Completed, Cancelled
    token_number = Column(String, nullable=True)
    
    patient = relationship("Patient", back_populates="appointments")
    doctor = relationship("User")
    appointment_type = relationship("AppointmentTypeConfig")
    consultation = relationship("Consultation", back_populates="appointment", uselist=False)
    vitals = relationship("Vitals", back_populates="appointment", uselist=False)

class PatientAISummary(Base):
    __tablename__ = "patient_ai_summaries"
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), index=True)
    summary_text = Column(Text, nullable=False)
    last_updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    patient = relationship("Patient", back_populates="ai_summaries")
