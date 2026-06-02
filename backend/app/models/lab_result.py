from sqlalchemy import Column, Integer, String, Date, Text, Float, Boolean, ForeignKey, DateTime, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base

class LabCatalog(Base):
    __tablename__ = "lab_catalog"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(Text, nullable=True)
    price = Column(Float, default=0.0)
    unit = Column(String, nullable=True)
    min_value = Column(Float, nullable=True)
    max_value = Column(Float, nullable=True)
    is_active = Column(Boolean, default=True)

class LabResult(Base):
    __tablename__ = "lab_results"
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    encounter_id = Column(Integer, ForeignKey("encounters.id"), nullable=True)
    catalog_id = Column(Integer, ForeignKey("lab_catalog.id"), nullable=True)
    test_name = Column(String)
    cost = Column(Float, nullable=True)
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
    catalog = relationship("LabCatalog")

class ComboLabTest(Base):
    __tablename__ = "combo_lab_tests"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    test_ids = Column(JSON) # List of catalog_ids
    price = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)
