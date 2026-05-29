from sqlalchemy import Column, Integer, String, Date, Text, Float, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base

class Encounter(Base):
    __tablename__ = "encounters"
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    doctor_id = Column(Integer, ForeignKey("users.id"))
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=True)
    encounter_date = Column(DateTime, default=datetime.utcnow)
    visit_number = Column(Integer, nullable=True)
    reason = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    quick_notes = Column(Text, nullable=True)
    advice = Column(Text, nullable=True)
    status = Column(String, default="Open") # Open, Closed
    created_at = Column(DateTime, default=datetime.utcnow)
    
    patient = relationship("Patient")
    doctor = relationship("User")
    appointment = relationship("Appointment")
    
    complaints = relationship("VisitComplaint", back_populates="encounter", cascade="all, delete-orphan")
    diagnoses = relationship("VisitDiagnosis", back_populates="encounter", cascade="all, delete-orphan")
    treatments = relationship("VisitTreatment", back_populates="encounter", cascade="all, delete-orphan")
    vitals = relationship("PatientVital", back_populates="encounter", cascade="all, delete-orphan")

class VitalConfiguration(Base):
    __tablename__ = "vital_configurations"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    data_type = Column(String) # numeric, string, date, computed
    formula = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)

class PatientVital(Base):
    __tablename__ = "patient_vitals"
    id = Column(Integer, primary_key=True, index=True)
    encounter_id = Column(Integer, ForeignKey("encounters.id"))
    vital_config_id = Column(Integer, ForeignKey("vital_configurations.id"))
    value = Column(String, nullable=True)
    
    encounter = relationship("Encounter", back_populates="vitals")
    vital_config = relationship("VitalConfiguration")

class VisitComplaint(Base):
    __tablename__ = "visit_complaints"
    id = Column(Integer, primary_key=True, index=True)
    encounter_id = Column(Integer, ForeignKey("encounters.id"))
    complaint = Column(String)
    from_date = Column(String, nullable=True)
    duration = Column(String, nullable=True)
    
    encounter = relationship("Encounter", back_populates="complaints")

class VisitDiagnosis(Base):
    __tablename__ = "visit_diagnoses"
    id = Column(Integer, primary_key=True, index=True)
    encounter_id = Column(Integer, ForeignKey("encounters.id"))
    diagnosis = Column(String)
    date = Column(String, nullable=True)
    
    encounter = relationship("Encounter", back_populates="diagnoses")

class VisitTreatment(Base):
    __tablename__ = "visit_treatments"
    id = Column(Integer, primary_key=True, index=True)
    encounter_id = Column(Integer, ForeignKey("encounters.id"))
    treatment = Column(String)
    due_date = Column(String, nullable=True)
    
    encounter = relationship("Encounter", back_populates="treatments")
