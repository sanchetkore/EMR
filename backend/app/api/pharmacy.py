from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy import cast, Date, or_, and_
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, date

from app.core.database import get_db
from app.models.prescription import Prescription
from app.models.encounter import Encounter
from app.models.patient import Patient
from app.models.user import User
from app.schemas.prescription import Prescription as PrescriptionSchema
from app.schemas.patient import Patient as PatientSchema
from app.schemas.user import User as UserSchema
from app.api.deps import RequirePermission
from app.core.websocket import manager
from app.api.queue import get_live_queue

router = APIRouter()

class PharmacyOrderResponse(BaseModel):
    id: int
    date_prescribed: datetime
    notes: Optional[str] = None
    status: Optional[str] = "Pending"
    patient: PatientSchema
    doctor: UserSchema
    items: List[dict] = []

    class Config:
        orm_mode = True

class OrderStatusUpdate(BaseModel):
    status: str

@router.get("/orders", response_model=List[PharmacyOrderResponse], dependencies=[Depends(RequirePermission("view_pharmacy"))])
def get_pharmacy_orders(status: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Prescription).options(
        joinedload(Prescription.patient),
        joinedload(Prescription.doctor),
        selectinload(Prescription.items)
    ).filter(or_(Prescription.encounter_id.is_(None), Prescription.encounter.has(Encounter.status == "Completed"))).order_by(Prescription.date_prescribed.desc())
    if status:
        query = query.filter(Prescription.status == status)
    else:
        query = query.filter(Prescription.status != "Cancelled")

    # Only include Fulfilled and Picked Up orders if they are from today
    now = datetime.utcnow()
    start_of_day = datetime(now.year, now.month, now.day, 0, 0, 0)
    end_of_day = datetime(now.year, now.month, now.day, 23, 59, 59)
    query = query.filter(
        or_(
            ~Prescription.status.in_(["Fulfilled", "Picked Up"]),
            and_(
                Prescription.status.in_(["Fulfilled", "Picked Up"]),
                Prescription.date_prescribed >= start_of_day,
                Prescription.date_prescribed <= end_of_day
            )
        )
    )

    prescriptions = query.all()

    response = []
    for p in prescriptions:
        # Build items
        items = []
        for item in p.items:
            items.append({
                "id": item.id,
                "molecule": item.molecule,
                "name": item.molecule,  # Provide name for backwards compatibility
                "morning": item.morning,
                "afternoon": item.afternoon,
                "evening": item.evening,
                "night": item.night,
                "when": item.when,
                "details": item.details
            })

        order = PharmacyOrderResponse(
            id=p.id,
            date_prescribed=p.date_prescribed,
            notes=p.notes,
            status=p.status,
            patient=PatientSchema.model_validate(p.patient, from_attributes=True),
            doctor=UserSchema.model_validate(p.doctor, from_attributes=True),
            items=items
        )
        response.append(order)

    return response

@router.get("/orders/{order_id}", response_model=PharmacyOrderResponse, dependencies=[Depends(RequirePermission("view_pharmacy"))])
def get_pharmacy_order(order_id: int, db: Session = Depends(get_db)):
    p = db.query(Prescription).options(
        joinedload(Prescription.patient),
        joinedload(Prescription.doctor),
        selectinload(Prescription.items)
    ).filter(Prescription.id == order_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Order not found")
    if p.encounter_id and p.encounter.status != "Completed":
        raise HTTPException(status_code=409, detail="This prescription has not been signed")

    items = []
    for item in p.items:
        items.append({
            "id": item.id,
            "molecule": item.molecule,
            "name": item.molecule,
            "morning": item.morning,
            "afternoon": item.afternoon,
            "evening": item.evening,
            "night": item.night,
            "when": item.when,
            "details": item.details
        })

    return PharmacyOrderResponse(
        id=p.id,
        date_prescribed=p.date_prescribed,
        notes=p.notes,
        status=p.status,
        patient=PatientSchema.model_validate(p.patient, from_attributes=True),
        doctor=UserSchema.model_validate(p.doctor, from_attributes=True),
        items=items
    )

@router.put("/orders/{order_id}/status", response_model=PharmacyOrderResponse, dependencies=[Depends(RequirePermission("manage_pharmacy"))])
def update_order_status(order_id: int, payload: OrderStatusUpdate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    p = db.query(Prescription).filter(Prescription.id == order_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Order not found")
    if p.encounter_id and p.encounter.status != "Completed":
        raise HTTPException(status_code=409, detail="This prescription has not been signed")

    valid_statuses = ["Pending", "Processing", "Fulfilled", "Cancelled", "Picked Up"]
    if payload.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of {valid_statuses}")

    p.status = payload.status
    db.commit()
    db.refresh(p)

    # Broadcast queue update
    queue_payload = get_live_queue(db)
    background_tasks.add_task(manager.broadcast, queue_payload)

    return get_pharmacy_order(order_id, db)
