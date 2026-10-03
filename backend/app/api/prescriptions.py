from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.database import get_db
from app.models.prescription import Prescription, PrescriptionItem
from app.models.encounter import Encounter
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
    if prescription.encounter_id:
        encounter = db.query(Encounter).filter(Encounter.id == prescription.encounter_id).first()
        if not encounter or encounter.patient_id != prescription.patient_id:
            raise HTTPException(status_code=422, detail="Prescription encounter does not belong to this patient")
        if encounter.status == "Completed":
            raise HTTPException(status_code=409, detail="Completed visit prescriptions require an amendment workflow")
    prescription_data = prescription.dict(exclude={"items"})
    db_prescription = Prescription(**prescription_data)
    db.add(db_prescription)
    db.flush()

    for item in prescription.items:
        db_item = PrescriptionItem(**item.dict(), prescription_id=db_prescription.id)
        db.add(db_item)

    db.commit()
    db.refresh(db_prescription)

    # Broadcast live queue update
    queue_payload = get_live_queue(db)
    background_tasks.add_task(manager.broadcast, queue_payload)

    # Send WhatsApp and SMS prescription notification
    from app.services.whatsapp_service import send_prescription_whatsapp
    from app.services.sms_service import send_prescription_sms
    background_tasks.add_task(send_prescription_whatsapp, db_prescription.patient_id, db_prescription.doctor_id, db_prescription.id)
    background_tasks.add_task(send_prescription_sms, db_prescription.patient_id, db_prescription.doctor_id)

    return db_prescription

@router.get("/{prescription_id}", response_model=PrescriptionSchema, dependencies=[Depends(RequirePermission("view_clinical"))])
def get_prescription(prescription_id: int, db: Session = Depends(get_db)):
    db_prescription = db.query(Prescription).filter(Prescription.id == prescription_id).first()
    if not db_prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")
    return db_prescription
