from datetime import datetime
import os
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.patient import Patient
from app.models.mobile import MobileDeviceToken, MobilePatientAlert
from app.api.mobile.deps import get_current_patient

router = APIRouter(prefix="/notifications", tags=["mobile-notifications"])
logger = logging.getLogger("mobile_notifications")

class RegisterTokenRequest(BaseModel):
    fcm_token: str
    platform: Optional[str] = "android"
    device_name: Optional[str] = "Android Device"

def dispatch_push_notification(patient_id: int, title: str, body: str, db: Session, data: Optional[dict] = None) -> bool:
    """Dispatches a push notification to registered FCM device tokens for the patient."""
    tokens = db.query(MobileDeviceToken).filter(MobileDeviceToken.patient_id == patient_id).all()
    if not tokens:
        logger.info("No devices registered for push notification")
        return False

    # Check for Firebase Admin credentials
    firebase_creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if firebase_creds_path and os.path.exists(firebase_creds_path):
        try:
            import firebase_admin
            from firebase_admin import messaging
            if not firebase_admin._apps:
                firebase_admin.initialize_app()

            for t in tokens:
                message = messaging.Message(
                    notification=messaging.Notification(
                        title=title,
                        body=body
                    ),
                    data={str(k): str(v) for k, v in (data or {}).items()},
                    token=t.fcm_token
                )
                messaging.send(message)
            logger.info("Push notification dispatched")
            return True
        except Exception as e:
            logger.warning("Push notification failed (%s)", type(e).__name__)
            return False
    else:
        logger.info("Push provider unavailable")
        return False

@router.post("/device-token")
def register_device_token(
    payload: RegisterTokenRequest,
    current_patient: Patient = Depends(get_current_patient),
    db: Session = Depends(get_db)
):
    token_str = payload.fcm_token.strip()
    if not token_str:
        raise HTTPException(status_code=400, detail="FCM token is required")

    existing = db.query(MobileDeviceToken).filter(MobileDeviceToken.fcm_token == token_str).first()
    if existing:
        existing.patient_id = current_patient.id
        existing.platform = payload.platform or "android"
        existing.device_name = payload.device_name or "Android Device"
        existing.updated_at = datetime.utcnow()
    else:
        new_token = MobileDeviceToken(
            patient_id=current_patient.id,
            fcm_token=token_str,
            platform=payload.platform or "android",
            device_name=payload.device_name or "Android Device"
        )
        db.add(new_token)

    db.commit()
    return {"status": "SUCCESS", "message": "Device token registered successfully"}

@router.get("/alerts")
def get_alerts(
    current_patient: Patient = Depends(get_current_patient),
    db: Session = Depends(get_db),
    latest_unread_only: bool = False,
):
    query = db.query(MobilePatientAlert).filter(
        MobilePatientAlert.patient_id == current_patient.id
    ).order_by(MobilePatientAlert.created_at.desc())
    if latest_unread_only:
        query = query.filter(MobilePatientAlert.is_read.is_not(True)).limit(1)
    alerts = query.all()

    return [
        {
            "id": a.id,
            "title": a.title,
            "message": a.message,
            "alertType": a.alert_type,
            "scheduledTimeLabel": a.scheduled_time_label or "Recent",
            "isRead": a.is_read,
            "isUrgent": a.is_urgent,
            "createdAtMillis": int(a.created_at.timestamp() * 1000)
        }
        for a in alerts
    ]

@router.put("/alerts/{alert_id}/read")
def mark_alert_as_read(
    alert_id: int,
    current_patient: Patient = Depends(get_current_patient),
    db: Session = Depends(get_db)
):
    alert = db.query(MobilePatientAlert).filter(
        MobilePatientAlert.id == alert_id,
        MobilePatientAlert.patient_id == current_patient.id
    ).first()

    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.is_read = True
    db.commit()
    return {"status": "SUCCESS", "message": "Alert marked as read"}
