from sqlalchemy import Column, Integer, String, Date, Text, Float, Boolean, ForeignKey, DateTime, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base

class Encounter(Base):
    __tablename__ = "encounters"
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), index=True)
    doctor_id = Column(Integer, ForeignKey("users.id"), index=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=True, index=True)
    encounter_date = Column(DateTime, default=datetime.utcnow)
    visit_number = Column(Integer, nullable=True)
    reason = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    draft_orders = Column(JSON, nullable=True)
    quick_notes = Column(Text, nullable=True)
    advice = Column(Text, nullable=True)
    status = Column(String, default="Open") # Open, Closed
    version = Column(Integer, nullable=False, default=1, server_default="1")
    signed_at = Column(DateTime, nullable=True)
    signed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    followup_days = Column(Integer, nullable=True)
    followup_date = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient")
    doctor = relationship("User", foreign_keys=[doctor_id])
    appointment = relationship("Appointment")

    complaints = relationship("VisitComplaint", back_populates="encounter", cascade="all, delete-orphan")
    diagnoses = relationship("VisitDiagnosis", back_populates="encounter", cascade="all, delete-orphan")
    treatments = relationship("VisitTreatment", back_populates="encounter", cascade="all, delete-orphan")
    vitals = relationship("PatientVital", back_populates="encounter", cascade="all, delete-orphan")
    prescriptions = relationship("Prescription", back_populates="encounter", cascade="all, delete-orphan")
    lab_results = relationship("LabResult", back_populates="encounter", cascade="all, delete-orphan")
    amendments = relationship("EncounterAmendment", back_populates="encounter", order_by="EncounterAmendment.created_at")
    lab_order_intent = relationship("VisitLabOrderIntent", back_populates="encounter", uselist=False)


class EncounterAmendment(Base):
    __tablename__ = "encounter_amendments"
    id = Column(Integer, primary_key=True, index=True)
    encounter_id = Column(Integer, ForeignKey("encounters.id"), nullable=False, index=True)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reason = Column(String(255), nullable=False)
    note = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    encounter = relationship("Encounter", back_populates="amendments")

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
    encounter_id = Column(Integer, ForeignKey("encounters.id"), index=True)
    vital_config_id = Column(Integer, ForeignKey("vital_configurations.id"), index=True)
    value = Column(String, nullable=True)

    encounter = relationship("Encounter", back_populates="vitals")
    vital_config = relationship("VitalConfiguration")

class VisitComplaint(Base):
    __tablename__ = "visit_complaints"
    id = Column(Integer, primary_key=True, index=True)
    encounter_id = Column(Integer, ForeignKey("encounters.id"), index=True)
    complaint = Column(String)
    from_date = Column(String, nullable=True)
    duration = Column(String, nullable=True)

    encounter = relationship("Encounter", back_populates="complaints")

class VisitDiagnosis(Base):
    __tablename__ = "visit_diagnoses"
    id = Column(Integer, primary_key=True, index=True)
    encounter_id = Column(Integer, ForeignKey("encounters.id"), index=True)
    diagnosis = Column(String)
    date = Column(String, nullable=True)

    encounter = relationship("Encounter", back_populates="diagnoses")

class VisitTreatment(Base):
    __tablename__ = "visit_treatments"
    id = Column(Integer, primary_key=True, index=True)
    encounter_id = Column(Integer, ForeignKey("encounters.id"), index=True)
    treatment = Column(String)
    due_date = Column(String, nullable=True)

    encounter = relationship("Encounter", back_populates="treatments")
