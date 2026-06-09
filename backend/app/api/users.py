from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
import os
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.models.user import User, Role, Permission, UserTab
from app.schemas.user import User as UserSchema, UserCreate, Role as RoleSchema, RoleCreate, Permission as PermissionSchema, PermissionCreate, UserTabsUpdate
from app.api.deps import RequirePermission, get_current_user
from app.core.security import get_password_hash

router = APIRouter()

@router.get("/permissions", response_model=List[PermissionSchema], dependencies=[Depends(RequirePermission("manage_users"))])
def get_permissions(db: Session = Depends(get_db)):
    return db.query(Permission).all()

@router.post("/permissions", response_model=PermissionSchema, dependencies=[Depends(RequirePermission("manage_users"))])
def create_permission(perm: PermissionCreate, db: Session = Depends(get_db)):
    db_perm = Permission(name=perm.name, description=perm.description)
    db.add(db_perm)
    db.commit()
    db.refresh(db_perm)
    return db_perm

@router.get("/roles", response_model=List[RoleSchema], dependencies=[Depends(RequirePermission("manage_users"))])
def get_roles(db: Session = Depends(get_db)):
    return db.query(Role).all()

@router.post("/roles", response_model=RoleSchema, dependencies=[Depends(RequirePermission("manage_users"))])
def create_role(role: RoleCreate, db: Session = Depends(get_db)):
    db_role = Role(name=role.name)
    perms = db.query(Permission).filter(Permission.id.in_(role.permission_ids)).all()
    db_role.permissions = perms
    db.add(db_role)
    db.commit()
    db.refresh(db_role)
    return db_role

@router.get("/", response_model=List[UserSchema], dependencies=[Depends(RequirePermission("manage_users"))])
def get_users(db: Session = Depends(get_db)):
    return db.query(User).all()

@router.get("/doctors", response_model=List[UserSchema])
def get_doctors(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Assuming role name 'Doctor'
    return db.query(User).join(Role).filter(Role.name == "Doctor").all()

@router.post("/", response_model=UserSchema, dependencies=[Depends(RequirePermission("manage_users"))])
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    db_user = User(
        username=user.username,
        email=user.email,
        hashed_password=get_password_hash(user.password),
        role_id=user.role_id,
        is_active=user.is_active,
        signature_path=user.signature_path
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

UPLOAD_DIR = "uploads"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

SECURE_UPLOAD_DIR = "secure_uploads"
if not os.path.exists(SECURE_UPLOAD_DIR):
    os.makedirs(SECURE_UPLOAD_DIR)

@router.post("/{user_id}/signature", response_model=UserSchema, dependencies=[Depends(RequirePermission("manage_users"))])
async def upload_signature(
    user_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    safe_filename = os.path.basename(file.filename.replace("\\", "/"))
    file_path = os.path.join(SECURE_UPLOAD_DIR, f"user_signature_{user_id}_{safe_filename}")
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
        
    if db_user.signature_path and os.path.exists(db_user.signature_path) and db_user.signature_path != file_path:
        try:
            os.remove(db_user.signature_path)
        except Exception:
            pass
            
    db_user.signature_path = file_path
    db.commit()
    db.refresh(db_user)
    return db_user

@router.get("/{user_id}/signature/image", dependencies=[Depends(get_current_user)])
def get_signature_image(user_id: int, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user or not db_user.signature_path:
        raise HTTPException(status_code=404, detail="Signature not found")
        
    if not os.path.exists(db_user.signature_path):
        raise HTTPException(status_code=404, detail="Signature file not found on server")
        
    return FileResponse(db_user.signature_path)

@router.get("/me", response_model=UserSchema)
def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

@router.put("/{user_id}", response_model=UserSchema, dependencies=[Depends(RequirePermission("manage_users"))])
def update_user(user_id: int, user_update: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    db_user.username = user_update.username
    db_user.email = user_update.email
    db_user.role_id = user_update.role_id
    db_user.is_active = user_update.is_active
    if user_update.password:
        db_user.hashed_password = get_password_hash(user_update.password)
        
    db.commit()
    db.refresh(db_user)
    return db_user

@router.delete("/{user_id}", dependencies=[Depends(RequirePermission("manage_users"))])
def delete_user(user_id: int, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    db_user.is_active = False # soft delete
    db.commit()
    return {"detail": "User deactivated successfully"}

@router.put("/{user_id}/tabs", response_model=UserSchema, dependencies=[Depends(RequirePermission("manage_users"))])
def update_user_tabs(user_id: int, tabs_update: UserTabsUpdate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Delete existing tabs
    db.query(UserTab).filter(UserTab.user_id == user_id).delete()
    
    # Insert new tabs
    new_tabs = [UserTab(user_id=user_id, tab_name=t) for t in set(tabs_update.tab_names)]
    db.add_all(new_tabs)
    db.commit()
    db.refresh(db_user)
    
    return db_user

@router.put("/roles/{role_id}", response_model=RoleSchema, dependencies=[Depends(RequirePermission("manage_users"))])
def update_role(role_id: int, role_update: RoleCreate, db: Session = Depends(get_db)):
    db_role = db.query(Role).filter(Role.id == role_id).first()
    if not db_role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    db_role.name = role_update.name
    perms = db.query(Permission).filter(Permission.id.in_(role_update.permission_ids)).all()
    db_role.permissions = perms
    
    db.commit()
    db.refresh(db_role)
    return db_role

@router.delete("/roles/{role_id}", dependencies=[Depends(RequirePermission("manage_users"))])
def delete_role(role_id: int, db: Session = Depends(get_db)):
    db_role = db.query(Role).filter(Role.id == role_id).first()
    if not db_role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    db.delete(db_role)
    db.commit()
    return {"detail": "Role deleted successfully"}
