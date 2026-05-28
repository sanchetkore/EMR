from sqlalchemy import Column, Integer, String, Date, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base

class Allergy(Base):
    __tablename__ = "allergies"
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    allergen = Column(String)
    reaction = Column(String, nullable=True)
    severity = Column(String, default="Mild") # Mild, Moderate, Severe
    onset_date = Column(Date, nullable=True)
    status = Column(String, default="Active") # Active, Inactive
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    patient = relationship("Patient")
