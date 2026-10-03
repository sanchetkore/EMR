from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Float, JSON, UniqueConstraint
from app.core.database import Base


class LISConnector(Base):
    __tablename__ = "lis_connector"

    id = Column(Integer, primary_key=True, default=1)
    encrypted_config = Column(Text, nullable=False)
    configured_mode = Column(String(32), default="CONNECTED")
    last_health_status = Column(String(32), default="UNKNOWN")
    last_health_check = Column(DateTime, nullable=True)
    last_catalog_refresh = Column(DateTime, nullable=True)


class PatientExternalIdentity(Base):
    __tablename__ = "patient_external_identities"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    lis_host = Column(String(128), nullable=False, default="")
    remote_patient_id = Column(String(64), nullable=False, index=True)
    opd_number = Column(String(64), nullable=True, index=True)
    verified_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("patient_id", "lis_host", name="uq_patient_lis_host"),
    )


class ExternalLabOrder(Base):
    __tablename__ = "external_lab_orders"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(64), unique=True, index=True, nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    lis_host = Column(String(128), nullable=False, default="")
    encounter_id = Column(Integer, nullable=True, index=True)
    source_id = Column(String(64), nullable=False, index=True)
    accession_number = Column(String(64), unique=True, index=True, nullable=False)
    test_codes = Column(JSON, nullable=False)
    package_codes = Column(JSON, nullable=True)
    payload_hash = Column(String(64), nullable=True, index=True)
    status = Column(String(32), default="PENDING")
    remote_order_id = Column(String(64), nullable=True)
    authoritative_price = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
