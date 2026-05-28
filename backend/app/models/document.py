from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base

class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    encounter_id = Column(Integer, ForeignKey("encounters.id"), nullable=True)
    type = Column(String) # ID, Form, Report
    title = Column(String)
    file_path = Column(String) # path to stored file or URL
    uploaded_by = Column(Integer, ForeignKey("users.id"))
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    patient = relationship("Patient")
    encounter = relationship("Encounter")
    uploader = relationship("User")
