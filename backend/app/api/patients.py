from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.models.patient import Patient
from app.schemas.patient import Patient as PatientSchema, PatientCreate
from app.api.deps import RequirePermission

router = APIRouter()

from sqlalchemy import or_

@router.get("/", response_model=List[PatientSchema], dependencies=[Depends(RequirePermission("view_patients"))])
def get_patients(search: str = None, db: Session = Depends(get_db)):
    query = db.query(Patient).filter(Patient.is_active == 1)
    if search:
        query = query.filter(or_(
            Patient.first_name.ilike(f"%{search}%"),
            Patient.last_name.ilike(f"%{search}%"),
            Patient.contact_number.ilike(f"%{search}%"),
            Patient.email.ilike(f"%{search}%")
        ))
    return query.all()

@router.post("/", response_model=PatientSchema, dependencies=[Depends(RequirePermission("manage_patients"))])
def create_patient(patient: PatientCreate, db: Session = Depends(get_db)):
    db_patient = Patient(**patient.dict())
    db.add(db_patient)
    db.commit()
    db.refresh(db_patient)
    return db_patient

@router.get("/{patient_id}", response_model=PatientSchema, dependencies=[Depends(RequirePermission("view_patients"))])
def get_patient(patient_id: int, db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient

@router.put("/{patient_id}", response_model=PatientSchema, dependencies=[Depends(RequirePermission("manage_patients"))])
def update_patient(patient_id: int, patient_update: PatientCreate, db: Session = Depends(get_db)):
    db_patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not db_patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    for var, value in vars(patient_update).items():
        setattr(db_patient, var, value)
        
    db.commit()
    db.refresh(db_patient)
    return db_patient

@router.delete("/{patient_id}", dependencies=[Depends(RequirePermission("manage_patients"))])
def delete_patient(patient_id: int, db: Session = Depends(get_db)):
    db_patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not db_patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    db_patient.is_active = 0 # soft delete
    db.commit()
    return {"detail": "Patient deleted successfully"}
