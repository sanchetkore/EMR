from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base

class Prescription(Base):
    __tablename__ = "prescriptions"
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), index=True)
    encounter_id = Column(Integer, ForeignKey("encounters.id"), nullable=True, index=True)
    doctor_id = Column(Integer, ForeignKey("users.id"), index=True)
    date_prescribed = Column(DateTime, default=datetime.utcnow, index=True)
    notes = Column(Text, nullable=True)
    status = Column(String, default="Pending") # Pending, Processing, Fulfilled, Cancelled
    
    patient = relationship("Patient")
    encounter = relationship("Encounter", back_populates="prescriptions")
    doctor = relationship("User")
    items = relationship("PrescriptionItem", back_populates="prescription", cascade="all, delete-orphan")

class PrescriptionItem(Base):
    __tablename__ = "prescription_items"
    id = Column(Integer, primary_key=True, index=True)
    prescription_id = Column(Integer, ForeignKey("prescriptions.id"), index=True)
    molecule = Column(String)
    morning = Column(String, nullable=True)
    afternoon = Column(String, nullable=True)
    evening = Column(String, nullable=True)
    night = Column(String, nullable=True)
    when = Column(String, nullable=True) # e.g. Before food, After food
    details = Column(Text, nullable=True)
    
    prescription = relationship("Prescription", back_populates="items")
