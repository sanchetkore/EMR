from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey, DateTime, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base

class MobileDeviceToken(Base):
    __tablename__ = "mobile_device_tokens"
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), index=True, nullable=False)
    fcm_token = Column(String(512), nullable=False, unique=True, index=True)
    platform = Column(String(32), default="android")
    device_name = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    patient = relationship("Patient")


class MobileOtp(Base):
    __tablename__ = "mobile_otps"
    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(32), index=True, nullable=False)
    otp_code = Column(String(16), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    is_used = Column(Boolean, default=False)


class MobileBloodPickup(Base):
    __tablename__ = "mobile_blood_pickups"
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), index=True, nullable=False)
    test_panel_title = Column(String(255), nullable=False)
    test_codes = Column(Text, nullable=True)
    fasting_required = Column(Boolean, default=False)
    pickup_date_iso = Column(String(32), nullable=False)
    pickup_date_label = Column(String(64), nullable=True)
    time_window = Column(String(64), nullable=False)
    address = Column(Text, nullable=False)
    notes = Column(Text, nullable=True)
    status = Column(String(32), default="SCHEDULED")  # SCHEDULED, COLLECTED, REPORT_READY, CANCELLED
    payment_status = Column(String(32), default="PENDING")  # PAID, PENDING
    amount_paid_cents = Column(Integer, default=0)
    payment_method_label = Column(String(64), nullable=True)
    transaction_id = Column(String(128), nullable=True)
    reminder_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient")


class MobilePickupCombo(Base):
    __tablename__ = "mobile_pickup_combos"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(80), nullable=False)
    test_codes = Column(JSON, nullable=False)


class MobilePatientAlert(Base):
    __tablename__ = "mobile_patient_alerts"
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), index=True, nullable=False)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    alert_type = Column(String(64), default="VISIT_REMINDER")  # VISIT_REMINDER, BLOOD_PICKUP, LAB_REPORT, PAYMENT
    scheduled_time_label = Column(String(64), nullable=True)
    is_read = Column(Boolean, default=False)
    is_urgent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient")


class MobilePaymentRecord(Base):
    __tablename__ = "mobile_payment_records"
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), index=True, nullable=False)
    reference_title = Column(String(255), nullable=False)
    category = Column(String(64), nullable=False)  # APPOINTMENT, BLOOD_PICKUP, INVOICE
    amount_cents = Column(Integer, nullable=False)
    insurance_saved_cents = Column(Integer, default=0)
    payment_method = Column(String(64), default="Razorpay")
    transaction_id = Column(String(128), nullable=False, unique=True, index=True)
    razorpay_order_id = Column(String(128), nullable=True, index=True)
    razorpay_payment_id = Column(String(128), nullable=True)
    status = Column(String(32), default="SUCCEEDED")
    timestamp_label = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient")

class MobilePatientLink(Base):
    __tablename__ = "mobile_patient_links"
    phone = Column(String(32), primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), primary_key=True)


class RevokedPatientToken(Base):
    __tablename__ = "revoked_patient_tokens"
    digest = Column(String(64), primary_key=True)
    expires_at = Column(DateTime, nullable=False, index=True)
