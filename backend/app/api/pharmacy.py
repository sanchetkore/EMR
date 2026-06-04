from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from app.core.database import get_db
from app.models.prescription import Prescription
from app.models.patient import Patient
from app.models.user import User
from app.schemas.prescription import Prescription as PrescriptionSchema
from app.schemas.patient import Patient as PatientSchema
from app.schemas.user import User as UserSchema
from app.api.deps import RequirePermission

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
    query = db.query(Prescription).order_by(Prescription.date_prescribed.desc())
    if status:
        query = query.filter(Prescription.status == status)
    
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
    p = db.query(Prescription).filter(Prescription.id == order_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Order not found")
        
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
def update_order_status(order_id: int, payload: OrderStatusUpdate, db: Session = Depends(get_db)):
    p = db.query(Prescription).filter(Prescription.id == order_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Order not found")
        
    valid_statuses = ["Pending", "Processing", "Fulfilled", "Cancelled"]
    if payload.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of {valid_statuses}")
        
    p.status = payload.status
    db.commit()
    db.refresh(p)
    
    return get_pharmacy_order(order_id, db)
