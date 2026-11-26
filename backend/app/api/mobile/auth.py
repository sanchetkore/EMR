from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
import hashlib
import hmac
import os
import secrets
import random
import re
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, literal_column, or_, select, update
import httpx
import jwt
from fastapi import Request as ApiRequest
from fastapi.security import HTTPAuthorizationCredentials
from app.core.limiter import limiter

from app.core.database import get_db
from app.core.security import SECRET_KEY
from app.services.whatsapp_service import _get_clinic_settings, _get_messaging_base_url
from app.models.patient import Patient, Appointment
from app.models.clinical import Vitals
from app.models.allergy import Allergy
from app.models.mobile import MobileOtp, MobilePatientLink, RevokedPatientToken
from app.api.mobile.deps import canonical_phone, get_current_patient, create_patient_token, decode_patient_token, patient_token_digest, security_scheme

@asynccontextmanager
async def otp_delivery_lifespan(app):
    with httpx.Client(timeout=8, limits=httpx.Limits(keepalive_expiry=60)) as client:
        yield {"mobile_otp_client": client}


router = APIRouter(prefix="/auth", tags=["mobile-auth"], lifespan=otp_delivery_lifespan)

SELF_SIGNUP_ENABLED = os.getenv("MOBILE_SELF_SIGNUP_ENABLED") == "true"


def otp_digest(phone: str, code: str) -> str:
    return hmac.new(SECRET_KEY.encode(), f"mobile-otp:{phone}:{code}".encode(), hashlib.sha256).hexdigest()[:16]


def deliver_otp(client: httpx.Client, base_url: str, api_key: str | None, channel: str, phone: str, code: str) -> None:
    template = os.getenv(f"MOBILE_OTP_{channel.upper()}_TEMPLATE_ID")
    variable = os.getenv(f"MOBILE_OTP_{channel.upper()}_VARIABLE", "1" if channel == "whatsapp" else "otp")
    if not (base_url and api_key and template):
        raise HTTPException(status_code=503, detail="This delivery method is unavailable")
    body = {"template_id": template, "to": phone, "variables": {variable: code}}
    if channel == "sms":
        body["route"] = "dlt"
        for field in ("sender_id", "entity_id"):
            value = os.getenv(f"MOBILE_OTP_SMS_{field.upper()}")
            if value:
                body[field] = value
    try:
        response = client.post(f"{base_url}/api/v1/messages/{channel}", json=body, headers={
            "x-api-key": api_key,
            "User-Agent": "Mozilla/5.0",
            "Idempotency-Key": secrets.token_hex(16),
        })
    except (httpx.RequestError, httpx.InvalidURL):
        raise HTTPException(status_code=503, detail="Unable to send verification code") from None
    if response.status_code != 202:
        raise HTTPException(status_code=503, detail="Unable to send verification code")


class RequestOtpRequest(BaseModel):
    phone_number: str
    channel: Literal["whatsapp", "sms"] = "whatsapp"


class VerifyOtpRequest(BaseModel):
    phone_number: str
    otp_code: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None

class UpdateProfileRequest(BaseModel):
    first_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(default=None, max_length=100)
    blood_group: Optional[str] = None
    address: Optional[str] = Field(default=None, max_length=2000)
    emergency_contact: Optional[str] = None
    emergency_phone: Optional[str] = None

def clean_phone(phone: str) -> str:
    return phone.strip().replace(" ", "").replace("-", "")

def format_patient_response(patient: Patient, db: Session) -> dict:
    full_name = f"{patient.first_name or ''} {patient.last_name or ''}".strip()
    if not full_name:
        full_name = "Patient"

    # Calculate age from DOB if present
    age = None
    if patient.dob:
        today = datetime.utcnow().date()
        age = today.year - patient.dob.year - ((today.month, today.day) < (patient.dob.month, patient.dob.day))

    latest_vitals = db.query(Vitals.bp, Vitals.pulse).outerjoin(Appointment, Vitals.appointment_id == Appointment.id).filter(
        Vitals.patient_id == patient.id,
        or_(Vitals.appointment_id.is_(None), Appointment.patient_id == patient.id),
    ).order_by(Appointment.appointment_time.desc(), Vitals.id.desc()).first()
    vitals = []
    if latest_vitals:
        if latest_vitals.bp:
            vitals.append(f"{latest_vitals.bp} mmHg")
        if latest_vitals.pulse is not None:
            vitals.append(f"{latest_vitals.pulse} bpm")
    allergies = db.query(Allergy.allergen).filter(Allergy.patient_id == patient.id, Allergy.status == "Active").all()
    return {
        "id": patient.id,
        "name": full_name,
        "first_name": patient.first_name or "",
        "last_name": patient.last_name or "",
        "patientId": patient.opd_number or f"AC-{patient.id:05d}",
        "opd_number": patient.opd_number or f"AC-{patient.id:05d}",
        "age": age,
        "gender": patient.gender or "Not Specified",
        "bloodGroup": patient.blood_group or "",
        "contactNumber": patient.contact_number or "",
        "email": patient.email or "",
        "allergiesSummary": ", ".join(item.allergen for item in allergies if item.allergen),
        "vitalsSummary": " / ".join(vitals),
        "homeAddress": patient.address or "",
        "insuranceProvider": ""
    }

@router.post("/request-otp")
@limiter.limit("10/minute")
def request_otp(request: ApiRequest, payload: RequestOtpRequest, db: Session = Depends(get_db)):
    if payload.channel == "sms":
        raise HTTPException(status_code=503, detail="SMS verification is temporarily unavailable")
    phone = clean_phone(payload.phone_number)
    if not re.fullmatch(r"\+?[0-9]{10,15}", phone):
        raise HTTPException(status_code=400, detail="Valid phone number is required")
    phone = canonical_phone(phone)

    # Serialize OTP issuance per recipient across PostgreSQL workers.
    if db.get_bind().dialect.name == "postgresql":
        lock_id = int.from_bytes(hashlib.sha256(f"mobile-otp:{phone}".encode()).digest()[:8], "big", signed=True)
        db.execute(select(func.pg_advisory_xact_lock(lock_id)))

    now = datetime.utcnow()
    recent, most_recent_unused = db.query(
        func.count(),
        func.max(MobileOtp.created_at).filter(MobileOtp.is_used.is_(False)),
    ).filter(
        MobileOtp.phone_number == phone,
        MobileOtp.created_at > now - timedelta(minutes=10),
    ).one()
    if most_recent_unused and most_recent_unused > now - timedelta(seconds=30):
        raise HTTPException(status_code=429, detail="Wait 30 seconds before requesting another WhatsApp code")
    if recent >= 5:
        raise HTTPException(status_code=429, detail="Too many code requests. Try again later.")
    otp = f"{secrets.randbelow(1_000_000):06d}"
    base_url = _get_messaging_base_url()
    api_key, _, _ = _get_clinic_settings(db)

    # Invalidate previous unused OTPs
    db.query(MobileOtp).filter(MobileOtp.phone_number == phone, MobileOtp.is_used.is_(False)).update(
        {"is_used": True}, synchronize_session=False
    )

    otp_record = MobileOtp(
        phone_number=phone,
        otp_code=otp_digest(phone, otp),
        expires_at=datetime.utcnow() + timedelta(minutes=10),
        is_used=False
    )
    db.add(otp_record)
    db.flush()
    otp_id = otp_record.id
    db.commit()

    try:
        deliver_otp(request.state.mobile_otp_client, base_url, api_key, payload.channel, phone, otp)
    except HTTPException:
        db.execute(update(MobileOtp).where(MobileOtp.id == otp_id).values(is_used=True))
        db.commit()
        raise

    return {
        "status": "OTP_SENT",
        "phone_number": phone,
        "expires_in_seconds": 600,
    }

@router.post("/verify-otp")
@limiter.limit("15/minute")
def verify_otp(request: ApiRequest, payload: VerifyOtpRequest, db: Session = Depends(get_db)):
    phone = clean_phone(payload.phone_number)
    submitted_otp = payload.otp_code.strip()

    if not re.fullmatch(r"\+?[0-9]{10,15}", phone) or not re.fullmatch(r"[0-9]{6}", submitted_otp):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP code")
    phone = canonical_phone(phone)

    now = datetime.utcnow()
    latest_valid_id = select(MobileOtp.id).where(
        MobileOtp.phone_number == phone,
        MobileOtp.is_used.is_(False),
        MobileOtp.expires_at > now,
    ).order_by(MobileOtp.id.desc()).limit(1).scalar_subquery()
    stored_digest = db.execute(update(MobileOtp).where(
        MobileOtp.id == latest_valid_id,
        MobileOtp.is_used.is_(False),
        MobileOtp.expires_at > now,
    ).values(is_used=True).returning(MobileOtp.otp_code)).scalar_one_or_none()
    if stored_digest is None:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP code")
    db.commit()
    if not hmac.compare_digest(stored_digest, otp_digest(phone, submitted_otp)):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP code")

    phone_matches = matching_patients(db, phone, active_only=False).order_by(Patient.id).all()
    matches = [patient for patient in phone_matches if patient.is_active == 1]
    if len(matches) > 1:
        return profile_choices(db, phone, matches)
    patient = matches[0] if matches else None
    if not patient and phone_matches:
        raise HTTPException(status_code=403, detail="Patient account is inactive")
    if patient is None and not SELF_SIGNUP_ENABLED:
        raise HTTPException(status_code=403, detail="Self-signup is disabled. Contact the clinic to register.")

    if not patient:
        # Auto-register patient if new
        fn = (payload.first_name or "Patient").strip()
        ln = (payload.last_name or "").strip()
        opd = f"AC-{random.randint(10000, 99999)}"
        patient = Patient(
            first_name=fn,
            last_name=ln,
            contact_number=phone,
            opd_number=opd,
            blood_group=None,
            address=None,
            is_active=1
        )
        db.add(patient)
        db.commit()
        db.refresh(patient)

    access_token = create_patient_token(patient_id=patient.id, phone=phone)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "patient": format_patient_response(patient, db)
    }

def matching_patients(db: Session, phone: str, active_only: bool = True):
    digits = canonical_phone(phone)
    variants = [digits]
    if len(digits) == 12 and digits.startswith("91"):
        variants.append(digits[2:])
    number = Patient.contact_number
    # Keep the fixed separators literal so this matches the database expression index.
    for separator in (" ", "-", "+", "(", ")"):
        number = func.replace(number, literal_column(f"'{separator}'"), literal_column("''"))
    query = db.query(Patient).filter(number.in_(variants))
    return query.filter(Patient.is_active == 1) if active_only else query


def profile_choices(db, phone, patients, current_id=None):
    phone = canonical_phone(phone)
    linked = {row.patient_id for row in db.query(MobilePatientLink).filter_by(phone=phone)}
    ticket = jwt.encode({"sub": phone, "aud": "mobile-profile-selection",
                         "exp": datetime.utcnow() + timedelta(minutes=10)}, SECRET_KEY, algorithm="HS256")
    return {"selection_ticket": ticket, "profiles": [
        {"id": p.id, "name": f"{p.first_name} {p.last_name or ''}".strip(),
         "linked": p.id in linked, "current": p.id == current_id} for p in patients]}


@router.get("/profiles")
def list_profiles(current: Patient = Depends(get_current_patient),
                  auth: HTTPAuthorizationCredentials = Depends(security_scheme), db: Session = Depends(get_db)):
    phone = decode_patient_token(auth.credentials)["phone"]
    if canonical_phone(phone) != canonical_phone(current.contact_number or ""):
        raise HTTPException(status_code=403, detail="Sign in with your current mobile number")
    return profile_choices(db, phone, matching_patients(db, phone).order_by(Patient.id).all(), current.id)


class ProfileSelection(BaseModel):
    selection_ticket: str
    patient_id: int
    dob: Optional[date] = None


@router.post("/select-profile")
@limiter.limit("8/minute")
def select_profile(request: ApiRequest, payload: ProfileSelection, db: Session = Depends(get_db)):
    try:
        claims = jwt.decode(payload.selection_ticket, SECRET_KEY, algorithms=["HS256"],
                            audience="mobile-profile-selection", options={"require": ["exp", "sub", "aud"]})
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=403, detail="Profile selection expired. Open the patient list again.")
    phone = claims["sub"]
    patient = matching_patients(db, phone).filter(Patient.id == payload.patient_id).with_for_update().first()
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient profile unavailable")
    if not db.get(MobilePatientLink, (phone, patient.id)):
        if not patient.dob:
            raise HTTPException(status_code=409, detail="Ask the clinic to add a date of birth to this record.")
        if payload.dob != patient.dob:
            raise HTTPException(status_code=403, detail="Date of birth does not match")
        db.add(MobilePatientLink(phone=phone, patient_id=patient.id))
        db.commit()
    return {"access_token": create_patient_token(patient.id, phone), "token_type": "bearer",
            "patient": format_patient_response(patient, db)}


@router.get("/me")
def get_my_profile(current_patient: Patient = Depends(get_current_patient), db: Session = Depends(get_db)):
    return format_patient_response(current_patient, db)


@router.post("/logout", status_code=204)
def logout_patient(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    db: Session = Depends(get_db),
):
    if not auth:
        raise HTTPException(status_code=401, detail="Authentication token required")
    claims = decode_patient_token(auth.credentials)
    digest = patient_token_digest(auth.credentials)
    db.query(RevokedPatientToken).filter(RevokedPatientToken.expires_at <= datetime.utcnow()).delete(
        synchronize_session=False
    )
    if db.get(RevokedPatientToken, digest) is None:
        expiry = datetime.fromtimestamp(claims["exp"], timezone.utc).replace(tzinfo=None)
        db.add(RevokedPatientToken(digest=digest, expires_at=expiry))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if db.get(RevokedPatientToken, digest) is None:
            raise
    return Response(status_code=204)

@router.put("/me")
def update_my_profile(
    payload: UpdateProfileRequest,
    current_patient: Patient = Depends(get_current_patient),
    db: Session = Depends(get_db)
):
    if payload.first_name is not None and not payload.first_name.strip():
        raise HTTPException(status_code=400, detail="First name is required")
    if payload.first_name is not None:
        current_patient.first_name = payload.first_name.strip()
    if payload.last_name is not None:
        current_patient.last_name = payload.last_name.strip()
    if payload.blood_group is not None:
        current_patient.blood_group = payload.blood_group.strip()
    if payload.address is not None:
        current_patient.address = payload.address.strip()
    if payload.emergency_contact is not None:
        current_patient.emergency_contact = payload.emergency_contact.strip()
    if payload.emergency_phone is not None:
        current_patient.emergency_phone = payload.emergency_phone.strip()

    db.commit()
    db.refresh(current_patient)
    return format_patient_response(current_patient, db)
