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
    contact_number = Column(String)
    email = Column(String, unique=True, index=True, nullable=True)
    blood_group = Column(String, nullable=True)
    emergency_contact = Column(String, nullable=True)
    emergency_phone = Column(String, nullable=True)
    address = Column(Text, nullable=True)
    is_active = Column(Integer, default=1) # 1 active, 0 inactive
    
    appointments = relationship("Appointment", back_populates="patient")

class Appointment(Base):
    __tablename__ = "appointments"
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    doctor_id = Column(Integer, ForeignKey("users.id")) # user with doctor role
    appointment_time = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="Scheduled") # Scheduled, Completed, Cancelled
    
    patient = relationship("Patient", back_populates="appointments")
    doctor = relationship("User")
    consultation = relationship("Consultation", back_populates="appointment", uselist=False)
    vitals = relationship("Vitals", back_populates="appointment", uselist=False)
