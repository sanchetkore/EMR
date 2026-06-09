from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.database import get_db
from app.models.prescription import Prescription, PrescriptionItem
from app.schemas.prescription import Prescription as PrescriptionSchema, PrescriptionCreate
from app.api.deps import RequirePermission
from app.core.websocket import manager
from app.api.queue import get_live_queue

router = APIRouter()

@router.get("/", response_model=List[PrescriptionSchema], dependencies=[Depends(RequirePermission("view_clinical"))])
def get_prescriptions(patient_id: Optional[int] = None, encounter_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(Prescription)
    if patient_id:
        query = query.filter(Prescription.patient_id == patient_id)
    if encounter_id:
        query = query.filter(Prescription.encounter_id == encounter_id)
    return query.all()

@router.post("/", response_model=PrescriptionSchema, dependencies=[Depends(RequirePermission("manage_clinical"))])
def create_prescription(prescription: PrescriptionCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    prescription_data = prescription.dict(exclude={"items"})
    db_prescription = Prescription(**prescription_data)
    db.add(db_prescription)
    db.commit()
    db.refresh(db_prescription)
    
    for item in prescription.items:
        db_item = PrescriptionItem(**item.dict(), prescription_id=db_prescription.id)
        db.add(db_item)
    
    db.commit()
    db.refresh(db_prescription)
    
    # Broadcast live queue update
    queue_payload = get_live_queue(db)
    background_tasks.add_task(manager.broadcast, queue_payload)
    
    return db_prescription

@router.get("/{prescription_id}", response_model=PrescriptionSchema, dependencies=[Depends(RequirePermission("view_clinical"))])
def get_prescription(prescription_id: int, db: Session = Depends(get_db)):
    db_prescription = db.query(Prescription).filter(Prescription.id == prescription_id).first()
    if not db_prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")
    return db_prescription
