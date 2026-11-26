from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError as JWTError
from sqlalchemy.orm import Session, joinedload, selectinload
from app.core.database import get_db
from app.core.security import decode_session_token, validate_session
from app.models.user import User, Role, Permission
from app.schemas.token import TokenData

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

def get_current_user(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_session_token(token, "access")
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    user = (
        db.query(User)
        .options(
            joinedload(User.role).selectinload(Role.permissions),
            selectinload(User.tabs)
        )
        .filter(User.username == token_data.username)
        .first()
    )
    if not validate_session(db, user, payload):
        raise credentials_exception
    return user

def get_current_active_user(current_user: User = Depends(get_current_user)):
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

class RequirePermission:
    def __init__(self, required_permission: str):
        self.required_permission = required_permission

    def __call__(self, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
        # Admin bypass
        if current_user.role and current_user.role.name == "Admin":
            return current_user

        if not current_user.role:
            raise HTTPException(status_code=403, detail="Not enough permissions")

        has_permission = any(perm.name == self.required_permission for perm in current_user.role.permissions)
        if not has_permission:
            raise HTTPException(status_code=403, detail="Not enough permissions")
        return current_user

async def get_current_user_ws(token: str):
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        payload = decode_session_token(token, "access")
        username: str = payload.get("sub")
        if username is None:
            return None
        user = db.query(User).filter(User.username == username).first()
        return user if validate_session(db, user, payload) else None
    except JWTError:
        return None
    finally:
        db.close()
