from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
import os
from typing import Optional
from app.core.database import get_db
from app.models.clinic import ClinicProfile
from app.schemas.clinic import ClinicProfile as ClinicProfileSchema, ClinicProfileUpdate
from app.api.deps import RequirePermission

router = APIRouter()
UPLOAD_DIR = "public_assets"

if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

@router.get("/", response_model=ClinicProfileSchema)
def get_clinic_profile(db: Session = Depends(get_db)):
    profile = db.query(ClinicProfile).filter(ClinicProfile.id == 1).first()
    if not profile:
        # Return empty profile if none exists
        return ClinicProfileSchema(id=1)

    # Construct the Pydantic model so we can safely compute the boolean
    response = ClinicProfileSchema.model_validate(profile)
    return response

from app.schemas.clinic import MessagingAuthInput
import json
import urllib.request
import urllib.error

@router.post("/messaging-auth", response_model=ClinicProfileSchema, dependencies=[Depends(RequirePermission("manage_settings"))])
def login_messaging_provider(auth_input: MessagingAuthInput, db: Session = Depends(get_db)):
    base_url = os.environ.get("MESSAGING_API_BASE_URL", "").rstrip("/")
    if not base_url:
        raise HTTPException(status_code=500, detail="MESSAGING_API_BASE_URL not configured")
    if not base_url.startswith("http"):
        base_url = f"http://{base_url}"

    endpoint = f"{base_url}/api/auth/api-key"
    payload = json.dumps(auth_input.model_dump()).encode("utf-8")
    req = urllib.request.Request(endpoint, data=payload, headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}, method="POST")

    try:
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            api_key = res_data.get("api_key")
            if not api_key:
                raise HTTPException(status_code=400, detail="No api_key returned from provider")
    except urllib.error.HTTPError as e:
        error_msg = e.read().decode("utf-8")
        status_code = 400 if e.code == 401 else e.code
        raise HTTPException(status_code=status_code, detail=f"Authentication failed: {error_msg}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Save the API key
    profile = db.query(ClinicProfile).filter(ClinicProfile.id == 1).first()
    if not profile:
        profile = ClinicProfile(id=1, notification_settings={"messaging_api_key": api_key})
        db.add(profile)
    else:
        current_settings = dict(profile.notification_settings or {})
        current_settings["messaging_api_key"] = api_key
        # SQLAlchemy needs to know the JSON column changed
        profile.notification_settings = current_settings

    db.commit()
    db.refresh(profile)
    return ClinicProfileSchema.model_validate(profile)

@router.delete("/messaging-auth", response_model=ClinicProfileSchema, dependencies=[Depends(RequirePermission("manage_settings"))])
def logout_messaging_provider(db: Session = Depends(get_db)):
    profile = db.query(ClinicProfile).filter(ClinicProfile.id == 1).first()
    if profile and profile.notification_settings:
        current_settings = dict(profile.notification_settings)
        if "messaging_api_key" in current_settings:
            del current_settings["messaging_api_key"]
            profile.notification_settings = current_settings
            db.commit()
            db.refresh(profile)

    return ClinicProfileSchema.model_validate(profile) if profile else ClinicProfileSchema(id=1)

@router.put("/", response_model=ClinicProfileSchema, dependencies=[Depends(RequirePermission("manage_settings"))])
def update_clinic_profile(profile_update: ClinicProfileUpdate, db: Session = Depends(get_db)):
    profile = db.query(ClinicProfile).filter(ClinicProfile.id == 1).first()

    # Preserve the messaging_api_key if it exists, as the frontend update payload might overwrite it
    existing_api_key = None
    if profile and profile.notification_settings:
        existing_api_key = profile.notification_settings.get("messaging_api_key")

    if not profile:
        profile = ClinicProfile(id=1, **profile_update.model_dump())
        db.add(profile)
    else:
        for var, value in profile_update.model_dump(exclude_unset=True).items():
            if value is not None:
                setattr(profile, var, value)

    # Restore the api key to the newly saved settings
    if existing_api_key:
        current_settings = dict(profile.notification_settings or {})
        current_settings["messaging_api_key"] = existing_api_key
        profile.notification_settings = current_settings

    db.commit()
    db.refresh(profile)
    return ClinicProfileSchema.model_validate(profile)

@router.post("/logo", response_model=ClinicProfileSchema, dependencies=[Depends(RequirePermission("manage_settings"))])
async def upload_clinic_logo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    safe_filename = os.path.basename(file.filename.replace("\\", "/"))
    file_path = os.path.join(UPLOAD_DIR, f"clinic_logo_{safe_filename}")
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    profile = db.query(ClinicProfile).filter(ClinicProfile.id == 1).first()
    if not profile:
        profile = ClinicProfile(id=1, logo_path=file_path)
        db.add(profile)
    else:
        if profile.logo_path and os.path.exists(profile.logo_path) and profile.logo_path != file_path:
            try:
                os.remove(profile.logo_path)
            except Exception:
                pass
        profile.logo_path = file_path

    db.commit()
    db.refresh(profile)
    return ClinicProfileSchema.model_validate(profile)
