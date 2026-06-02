from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
import os
from typing import Optional
from app.core.database import get_db
from app.models.clinic import ClinicProfile
from app.schemas.clinic import ClinicProfile as ClinicProfileSchema, ClinicProfileUpdate
from app.api.deps import RequirePermission

router = APIRouter()
UPLOAD_DIR = "uploads"

if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

@router.get("/", response_model=ClinicProfileSchema)
def get_clinic_profile(db: Session = Depends(get_db)):
    profile = db.query(ClinicProfile).filter(ClinicProfile.id == 1).first()
    if not profile:
        # Return empty profile if none exists
        return ClinicProfileSchema(id=1)
    return profile

@router.put("/", response_model=ClinicProfileSchema, dependencies=[Depends(RequirePermission("manage_settings"))])
def update_clinic_profile(profile_update: ClinicProfileUpdate, db: Session = Depends(get_db)):
    profile = db.query(ClinicProfile).filter(ClinicProfile.id == 1).first()
    
    if not profile:
        profile = ClinicProfile(id=1, **profile_update.dict())
        db.add(profile)
    else:
        for var, value in vars(profile_update).items():
            if value is not None:
                setattr(profile, var, value)
                
    db.commit()
    db.refresh(profile)
    return profile

@router.post("/logo", response_model=ClinicProfileSchema, dependencies=[Depends(RequirePermission("manage_settings"))])
async def upload_clinic_logo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    file_path = os.path.join(UPLOAD_DIR, f"clinic_logo_{file.filename}")
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
        
    profile = db.query(ClinicProfile).filter(ClinicProfile.id == 1).first()
    if not profile:
        profile = ClinicProfile(id=1, logo_path=file_path)
        db.add(profile)
    else:
        # Optional: delete old logo file if it exists
        if profile.logo_path and os.path.exists(profile.logo_path) and profile.logo_path != file_path:
            try:
                os.remove(profile.logo_path)
            except Exception:
                pass
        profile.logo_path = file_path
        
    db.commit()
    db.refresh(profile)
    return profile
