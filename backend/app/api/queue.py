from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, Request
from app.core.limiter import limiter
from sqlalchemy.orm import Session, joinedload
from app.core.database import get_db
from datetime import datetime, timedelta, timezone
from app.models.patient import Appointment
from app.models.prescription import Prescription
from app.models.encounter import Encounter
from app.core.websocket import manager
from datetime import date, datetime
from sqlalchemy import cast, Date, or_

router = APIRouter()

def get_live_queue(db: Session):
    # Calculate today's date using IST (UTC+5:30) to avoid UTC rollover issues
    ist = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(ist)

    today_start = datetime(now_ist.year, now_ist.month, now_ist.day, 0, 0, 0)
    today_end = datetime(now_ist.year, now_ist.month, now_ist.day, 23, 59, 59)

    appointments = db.query(Appointment).options(
        joinedload(Appointment.patient),
        joinedload(Appointment.doctor)
    ).filter(
        Appointment.appointment_time >= today_start,
        Appointment.appointment_time <= today_end
    ).order_by(Appointment.appointment_time.asc()).all()

    ongoing = []
    waiting = []

    for apt in appointments:
        # Skip appointments that are done, cancelled, or no-show
        if apt.status in ["Completed", "Cancelled", "No Show"]:
            continue

        # The public display feed identifies a place in the queue, not the patient.
        patient_name = f"Token {apt.token_number}" if apt.token_number else "Next patient"

        doctor_name = "Unassigned"
        if apt.doctor:
            # Check if doctor has a basic structure from schema or just use username
            doctor_name = f"Dr. {apt.doctor.username}"

        payload = {
            "appointment_id": apt.id,
            "patient_name": patient_name,
            "opd_number": None,
            "token_number": apt.token_number,
            "doctor_name": doctor_name,
            "time": apt.appointment_time.strftime("%H:%M"),
            "status": apt.status
        }

        if apt.status == "Ongoing":
            ongoing.append(payload)
        elif apt.status in ["Scheduled", "Waiting"]:
            waiting.append(payload)

    # Fetch prescriptions for the queue, chronologically, only for today
    prescriptions = db.query(Prescription).options(
        joinedload(Prescription.patient)
    ).filter(
        Prescription.status != "Cancelled",
        or_(Prescription.encounter_id.is_(None), Prescription.encounter.has(Encounter.status == "Completed")),
        Prescription.date_prescribed >= today_start,
        Prescription.date_prescribed <= today_end
    ).order_by(Prescription.date_prescribed.asc()).all()

    pharmacy_waiting = []
    pharmacy_processing = []
    pharmacy_fulfilled = []

    for p in prescriptions:
        # Skip Picked Up, they should disappear from the queue entirely
        if p.status == "Picked Up":
            continue

        patient_name = f"Prescription {p.id}"

        rx_payload = {
            "prescription_id": p.id,
            "patient_name": patient_name,
            "opd_number": None,
            "time": p.date_prescribed.strftime("%H:%M"),
            "status": p.status
        }

        if p.status == "Pending":
            pharmacy_waiting.append(rx_payload)
        elif p.status == "Processing":
            pharmacy_processing.append(rx_payload)
        elif p.status == "Fulfilled":
            pharmacy_fulfilled.append(rx_payload)

    return {
        "ongoing": ongoing[:10],
        "waiting": waiting[:10],
        "pharmacy_waiting": pharmacy_waiting[:10],
        "pharmacy_processing": pharmacy_processing[:10],
        "pharmacy_fulfilled": pharmacy_fulfilled[:10]
    }

@router.get("/live")
@limiter.limit("60/minute")
def get_live_queue_rest(request: Request, db: Session = Depends(get_db)):
    """REST endpoint for the TV display to fetch the initial queue state on page load"""
    return get_live_queue(db)

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for the TV display to listen to live updates"""
    await manager.connect(websocket)
    try:
        # Keep the connection open and listen for client messages (optional, usually ping/pong)
        while True:
            data = await websocket.receive_text()
            # We don't really expect the TV to send us data, but we must await receive
            # to detect when the client disconnects.
    except WebSocketDisconnect:
        manager.disconnect(websocket)
