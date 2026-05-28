from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base

class Prescription(Base):
    __tablename__ = "prescriptions"
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    encounter_id = Column(Integer, ForeignKey("encounters.id"), nullable=True)
    doctor_id = Column(Integer, ForeignKey("users.id"))
    date_prescribed = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text, nullable=True)
    
    patient = relationship("Patient")
    encounter = relationship("Encounter")
    doctor = relationship("User")
    items = relationship("PrescriptionItem", back_populates="prescription", cascade="all, delete-orphan")

class PrescriptionItem(Base):
    __tablename__ = "prescription_items"
    id = Column(Integer, primary_key=True, index=True)
    prescription_id = Column(Integer, ForeignKey("prescriptions.id"))
    drug_name = Column(String)
    dosage = Column(String)
    frequency = Column(String)
    duration = Column(String, nullable=True)
    quantity = Column(Integer, nullable=True)
    instructions = Column(Text, nullable=True)
    
    prescription = relationship("Prescription", back_populates="items")
