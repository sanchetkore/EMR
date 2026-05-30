from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.patient import Appointment
from app.core.websocket import manager
from datetime import date
from sqlalchemy import cast, Date

router = APIRouter()

def get_live_queue(db: Session):
    # Get all appointments for today
    today = date.today()
    appointments = db.query(Appointment).filter(
        cast(Appointment.appointment_time, Date) == today
    ).order_by(Appointment.appointment_time.asc()).all()

    ongoing = []
    waiting = []
    
    for apt in appointments:
        # Skip appointments that are done, cancelled, or no-show
        if apt.status in ["Completed", "Cancelled", "No Show"]:
            continue
            
        # Build payload with patient name and doctor name
        patient_name = f"{apt.patient.first_name} {apt.patient.last_name}" if apt.patient else "Unknown Patient"
        
        doctor_name = "Unassigned"
        if apt.doctor:
            # Check if doctor has a basic structure from schema or just use username
            doctor_name = f"Dr. {apt.doctor.username}"
            
        payload = {
            "appointment_id": apt.id,
            "patient_name": patient_name,
            "doctor_name": doctor_name,
            "time": apt.appointment_time.strftime("%H:%M"),
            "status": apt.status
        }
        
        if apt.status == "Ongoing":
            ongoing.append(payload)
        elif apt.status in ["Scheduled", "Waiting"]:
            waiting.append(payload)
            
    return {
        "ongoing": ongoing,
        "waiting": waiting
    }

@router.get("/live")
def get_live_queue_rest(db: Session = Depends(get_db)):
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
