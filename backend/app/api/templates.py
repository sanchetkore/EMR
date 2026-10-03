from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
import os
import urllib.request
import urllib.error
import json

from app.core.database import get_db
from app.models.clinic import ClinicProfile
from app.api.deps import RequirePermission

router = APIRouter()

def get_messaging_base_url():
    base_url = os.environ.get("MESSAGING_API_BASE_URL", "").rstrip("/")
    if not base_url:
        raise HTTPException(status_code=500, detail="MESSAGING_API_BASE_URL not configured")
    if not base_url.startswith("http"):
        base_url = f"http://{base_url}"
    return base_url

def get_messaging_api_key(db: Session):
    profile = db.query(ClinicProfile).filter(ClinicProfile.id == 1).first()
    if not profile or not profile.notification_settings:
        raise HTTPException(status_code=400, detail="Messaging provider not connected")
    api_key = profile.notification_settings.get("messaging_api_key")
    if not api_key:
        raise HTTPException(status_code=400, detail="Messaging provider not connected")
    return api_key

@router.post("/sync", dependencies=[Depends(RequirePermission("manage_settings"))])
def sync_templates(db: Session = Depends(get_db)):
    base_url = get_messaging_base_url()
    api_key = get_messaging_api_key(db)

    endpoint = f"{base_url}/api/v1/templates"
    req = urllib.request.Request(endpoint, headers={"x-api-key": api_key, "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}, method="GET")

    try:
        from app.models.whatsapp_template import WhatsappTemplate
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode("utf-8"))

            whatsapp_list = res_data.get("whatsapp", [])
            for tmpl in whatsapp_list:
                existing = db.query(WhatsappTemplate).filter(WhatsappTemplate.name == tmpl.get("name")).first()
                if existing:
                    existing.body = tmpl.get("content", "")
                    existing.status = tmpl.get("status", "")
                    existing.category = tmpl.get("category", "")
                    existing.language = tmpl.get("language", "")
                else:
                    new_tmpl = WhatsappTemplate(
                        name=tmpl.get("name"),
                        body=tmpl.get("content", ""),
                        status=tmpl.get("status", ""),
                        category=tmpl.get("category", ""),
                        language=tmpl.get("language", "")
                    )
                    db.add(new_tmpl)
            db.commit()

            return {"success": True, "message": f"Synced {len(whatsapp_list)} WhatsApp templates"}
    except urllib.error.HTTPError as e:
        error_msg = e.read().decode("utf-8")
        status_code = 400 if e.code == 401 else e.code
        raise HTTPException(status_code=status_code, detail=f"Failed to sync templates: {error_msg}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/", dependencies=[Depends(RequirePermission("manage_settings"))])
def get_templates(db: Session = Depends(get_db)):
    base_url = get_messaging_base_url()
    api_key = get_messaging_api_key(db)

    endpoint = f"{base_url}/api/v1/templates"
    req = urllib.request.Request(endpoint, headers={"x-api-key": api_key, "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}, method="GET")

    try:
        from app.models.whatsapp_template import WhatsappTemplate

        with urllib.request.urlopen(req) as response:
            remote_templates = json.loads(response.read().decode("utf-8"))
            sms_templates = remote_templates.get("sms", {})

        whatsapp_templates = db.query(WhatsappTemplate).all()
        whatsapp_data = [
            {
                "id": t.id,
                "name": t.name,
                "category": t.category,
                "language": t.language,
                "content": t.body, # Map body to content for UI compatibility
                "body": t.body,
                "status": t.status,
            }
            for t in whatsapp_templates
        ]

        return {
            "sms": sms_templates,
            "whatsapp": whatsapp_data
        }
    except urllib.error.HTTPError as e:
        error_msg = e.read().decode("utf-8")
        status_code = 400 if e.code == 401 else e.code
        raise HTTPException(status_code=status_code, detail=f"Failed to fetch templates: {error_msg}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/balance", dependencies=[Depends(RequirePermission("manage_settings"))])
def get_message_balance(db: Session = Depends(get_db)):
    base_url = get_messaging_base_url()
    api_key = get_messaging_api_key(db)

    endpoint = f"{base_url}/api/v1/messages/balance"
    req = urllib.request.Request(endpoint, headers={"x-api-key": api_key, "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}, method="GET")

    try:
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            return res_data
    except urllib.error.HTTPError as e:
        error_msg = e.read().decode("utf-8")
        status_code = 400 if e.code == 401 else e.code
        raise HTTPException(status_code=status_code, detail=f"Failed to fetch message balance: {error_msg}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
