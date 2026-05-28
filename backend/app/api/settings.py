from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.models.settings import SystemSetting
from app.schemas.settings import SystemSetting as SystemSettingSchema, SystemSettingCreate
from app.api.deps import RequirePermission, get_current_user

router = APIRouter()

@router.get("/", response_model=List[SystemSettingSchema])
def get_settings(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    return db.query(SystemSetting).all()

@router.post("/", response_model=SystemSettingSchema, dependencies=[Depends(RequirePermission("manage_users"))])
def update_setting(setting: SystemSettingCreate, db: Session = Depends(get_db)):
    db_setting = db.query(SystemSetting).filter(SystemSetting.key == setting.key).first()
    if db_setting:
        db_setting.value = setting.value
    else:
        db_setting = SystemSetting(key=setting.key, value=setting.value)
        db.add(db_setting)
    db.commit()
    db.refresh(db_setting)
    return db_setting
