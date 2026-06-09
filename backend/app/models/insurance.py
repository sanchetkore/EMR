from sqlalchemy import Column, Integer, String, Date, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base

class Insurance(Base):
    __tablename__ = "insurances"
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), index=True)
    provider = Column(String)
    policy_number = Column(String)
    group_number = Column(String, nullable=True)
    copay = Column(Float, default=0.0)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    status = Column(String, default="Active") # Active, Inactive
    created_at = Column(DateTime, default=datetime.utcnow)
    
    patient = relationship("Patient")
