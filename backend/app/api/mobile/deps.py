from datetime import datetime, timedelta
import hashlib
import secrets
from typing import Optional
import jwt
from jwt import InvalidTokenError as JWTError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.patient import Patient
from app.models.mobile import RevokedPatientToken

from app.core.security import SECRET_KEY
ALGORITHM = "HS256"
PATIENT_ACCESS_TOKEN_EXPIRE_DAYS = 30

security_scheme = HTTPBearer(auto_error=False)

def canonical_phone(phone: str) -> str:
    digits = phone.strip().translate(str.maketrans("", "", " -+()"))
    return "91" + digits if len(digits) == 10 else digits


def patient_token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def create_patient_token(patient_id: int, phone: str, expires_delta: Optional[timedelta] = None) -> str:
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=PATIENT_ACCESS_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": f"patient:{patient_id}",
        "patient_id": patient_id,
        "phone": phone,
        "role": "patient",
        "jti": secrets.token_urlsafe(24),
        "exp": expire,
        "iat": datetime.utcnow()
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def decode_patient_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"require": ["exp", "sub"]})
        if (payload.get("role") != "patient" or type(payload.get("patient_id")) is not int
                or payload.get("sub") != f"patient:{payload.get('patient_id')}"
                or not isinstance(payload.get("phone"), str) or not payload["phone"]):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid patient token")
        return payload
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")

def get_current_patient(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    db: Session = Depends(get_db)
) -> Patient:
    if not auth or not auth.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token required",
            headers={"WWW-Authenticate": "Bearer"}
        )
    payload = decode_patient_token(auth.credentials)
    patient_id = payload.get("patient_id")
    revoked = db.query(RevokedPatientToken.digest).filter(
        RevokedPatientToken.digest == patient_token_digest(auth.credentials)
    ).exists()
    patient = db.query(Patient).filter(Patient.id == patient_id, ~revoked).first()
    if (not patient or patient.is_active != 1
            or canonical_phone(payload["phone"]) != canonical_phone(patient.contact_number or "")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Patient account not found or inactive")
    return patient
