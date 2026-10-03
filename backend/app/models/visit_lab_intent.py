from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.core.database import Base


class VisitLabOrderIntent(Base):
    __tablename__ = "visit_lab_order_intents"

    id = Column(Integer, primary_key=True)
    encounter_id = Column(Integer, ForeignKey("encounters.id"), nullable=False, unique=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    requested_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    source_id = Column(String(64), nullable=False, unique=True)
    connection_id = Column(String(64), nullable=False)
    test_codes = Column(JSON, nullable=False)
    package_codes = Column(JSON, nullable=False, default=list)
    notes = Column(Text, nullable=True)
    status = Column(String(24), nullable=False, default="PENDING")
    attempt_count = Column(Integer, nullable=False, default=0)
    retry_after = Column(DateTime, nullable=True)
    lease_expires_at = Column(DateTime, nullable=True)
    remote_order_id = Column(String(64), nullable=True)
    accession_number = Column(String(64), nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    encounter = relationship("Encounter", back_populates="lab_order_intent")
