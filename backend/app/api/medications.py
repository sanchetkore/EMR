from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.database import get_db
from app.models.medication import Medication
from app.schemas.medication import Medication as MedicationSchema, MedicationCreate
from app.api.deps import RequirePermission

router = APIRouter()

@router.get("/patients/{patient_id}/medications", response_model=List[MedicationSchema], dependencies=[Depends(RequirePermission("view_clinical"))])
def get_medications(patient_id: int, db: Session = Depends(get_db)):
    return db.query(Medication).filter(Medication.patient_id == patient_id).all()

@router.post("/patients/{patient_id}/medications", response_model=MedicationSchema, dependencies=[Depends(RequirePermission("manage_clinical"))])
def create_medication(patient_id: int, medication: MedicationCreate, db: Session = Depends(get_db)):
    if medication.patient_id != patient_id:
        raise HTTPException(status_code=400, detail="Patient ID mismatch")
    db_medication = Medication(**medication.dict())
    db.add(db_medication)
    db.commit()
    db.refresh(db_medication)
    return db_medication

@router.get("/medications/{medication_id}", response_model=MedicationSchema, dependencies=[Depends(RequirePermission("view_clinical"))])
def get_medication(medication_id: int, db: Session = Depends(get_db)):
    db_medication = db.query(Medication).filter(Medication.id == medication_id).first()
    if not db_medication:
        raise HTTPException(status_code=404, detail="Medication not found")
    return db_medication

@router.put("/medications/{medication_id}", response_model=MedicationSchema, dependencies=[Depends(RequirePermission("manage_clinical"))])
def update_medication(medication_id: int, medication_update: MedicationCreate, db: Session = Depends(get_db)):
    db_medication = db.query(Medication).filter(Medication.id == medication_id).first()
    if not db_medication:
        raise HTTPException(status_code=404, detail="Medication not found")
    
    for var, value in medication_update.model_dump(exclude_unset=True).items():
        setattr(db_medication, var, value)
        
    db.commit()
    db.refresh(db_medication)
    return db_medication

@router.delete("/medications/{medication_id}", dependencies=[Depends(RequirePermission("manage_clinical"))])
def delete_medication(medication_id: int, db: Session = Depends(get_db)):
    db_medication = db.query(Medication).filter(Medication.id == medication_id).first()
    if not db_medication:
        raise HTTPException(status_code=404, detail="Medication not found")
    db_medication.status = "Discontinued"
    db.commit()
    return {"detail": "Medication discontinued successfully"}
