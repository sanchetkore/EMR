from datetime import datetime, timedelta
import hashlib
import secrets
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from jwt import InvalidTokenError as JWTError
from app.core.limiter import limiter
from app.core.database import get_db
from app.core.security import (
    verify_password, create_access_token, create_refresh_token,
    ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_MINUTES,
    credential_version, decode_session_token, validate_session,
    LEGACY_DEMO_PASSWORDS,
)
from app.models.user import User, AuthSession
from app.schemas.token import Token, TokenRefresh

router = APIRouter()


def unauthorized():
    return HTTPException(401, "Could not validate credentials", headers={"WWW-Authenticate": "Bearer"})


def token_pair(user, session):
    remaining = session.expires_at - datetime.utcnow()
    if remaining.total_seconds() <= 0:
        raise unauthorized()
    claims = {"sub": user.username, "sid": session.id, "cv": credential_version(user)}
    access = create_access_token(claims, min(remaining, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)))
    refresh = create_refresh_token({**claims, "jti": secrets.token_urlsafe(32)}, remaining)
    return {"access_token": access, "token_type": "bearer", "refresh_token": refresh}


@router.post("/login", response_model=Token)
@limiter.limit("5/minute")
def login_for_access_token(request: Request, db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()):
    user = db.query(User).filter(User.username == form_data.username).first()
    if (not user or not user.is_active
            or form_data.password == LEGACY_DEMO_PASSWORDS.get(user.username)
            or not verify_password(form_data.password, user.hashed_password)):
        raise unauthorized()
    session = AuthSession(id=secrets.token_urlsafe(32), user_id=user.id,
                          expires_at=datetime.utcnow() + timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES))
    pair = token_pair(user, session)
    session.refresh_digest = hashlib.sha256(pair["refresh_token"].encode()).hexdigest()
    db.add(session)
    db.commit()
    return pair


@router.post("/refresh", response_model=Token)
@limiter.limit("10/minute")
def refresh_token(request: Request, token_data: TokenRefresh, db: Session = Depends(get_db)):
    try:
        payload = decode_session_token(token_data.refresh_token, "refresh")
    except JWTError:
        raise unauthorized()
    user = db.query(User).filter(User.username == payload["sub"]).first()
    if not validate_session(db, user, payload):
        raise unauthorized()
    session = db.query(AuthSession).filter(AuthSession.id == payload["sid"]).first()
    pair = token_pair(user, session)
    # Compare-and-swap makes a refresh token single-use even across workers.
    updated = db.query(AuthSession).filter(
        AuthSession.id == session.id, AuthSession.revoked.is_(False),
        AuthSession.expires_at > datetime.utcnow(),
        AuthSession.refresh_digest == hashlib.sha256(token_data.refresh_token.encode()).hexdigest(),
    ).update({AuthSession.refresh_digest: hashlib.sha256(pair["refresh_token"].encode()).hexdigest()}, synchronize_session=False)
    if updated != 1:
        db.query(AuthSession).filter(AuthSession.id == session.id).update({AuthSession.revoked: True})
        db.commit()
        raise unauthorized()
    db.commit()
    return pair
