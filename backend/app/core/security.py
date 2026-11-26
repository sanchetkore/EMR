from datetime import datetime, timedelta
from typing import Optional
import jwt
from jwt import InvalidTokenError as JWTError
from passlib.context import CryptContext
import os
import hashlib
import hmac

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY or len(SECRET_KEY.strip().encode("utf-8")) < 32:
    raise ValueError("SECRET_KEY must contain at least 32 UTF-8 bytes")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Recognize previously seeded credentials so upgrades can revoke their sessions.
LEGACY_DEMO_PASSWORDS = {
    "admin": "admin123",
    "doctor": "doctor123",
    "frontdesk": "frontdesk123",
    "pharmacist": "pharmacist123",
}


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire, "token_use": "access"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "token_use": "refresh"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def credential_version(user):
    return hmac.new(SECRET_KEY.encode(), user.hashed_password.encode(), hashlib.sha256).hexdigest()


def decode_session_token(token, token_use):
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM],
                         options={"require": ["exp", "sub"]})
    if payload.get("token_use") != token_use or not isinstance(payload.get("sid"), str):
        raise JWTError("Invalid token purpose or session")
    return payload


def validate_session(db, user, payload):
    from app.models.user import AuthSession
    if not user or not user.is_active:
        return False
    if not hmac.compare_digest(str(payload.get("cv", "")), credential_version(user)):
        return False
    return db.query(AuthSession).filter(
        AuthSession.id == payload["sid"], AuthSession.user_id == user.id,
        AuthSession.revoked.is_(False), AuthSession.expires_at > datetime.utcnow(),
    ).first() is not None
