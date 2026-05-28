from sqlalchemy import Column, Integer, String, Date, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base

class LabResult(Base):
    __tablename__ = "lab_results"
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    encounter_id = Column(Integer, ForeignKey("encounters.id"), nullable=True)
    test_name = Column(String)
    result_value = Column(String, nullable=True)
    unit = Column(String, nullable=True)
    reference_range = Column(String, nullable=True)
    status = Column(String, default="Pending") # Pending, Completed
    ordered_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    ordered_date = Column(DateTime, default=datetime.utcnow)
    result_date = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    
    patient = relationship("Patient")
    encounter = relationship("Encounter")
    orderer = relationship("User")
