from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.database import get_db
from app.models.immunization import Immunization
from app.schemas.immunization import Immunization as ImmunizationSchema, ImmunizationCreate
from app.api.deps import RequirePermission

router = APIRouter()

@router.get("/patients/{patient_id}/immunizations", response_model=List[ImmunizationSchema], dependencies=[Depends(RequirePermission("view_clinical"))])
def get_immunizations(patient_id: int, db: Session = Depends(get_db)):
    return db.query(Immunization).filter(Immunization.patient_id == patient_id).all()

@router.post("/patients/{patient_id}/immunizations", response_model=ImmunizationSchema, dependencies=[Depends(RequirePermission("manage_clinical"))])
def create_immunization(patient_id: int, immunization: ImmunizationCreate, db: Session = Depends(get_db)):
    if immunization.patient_id != patient_id:
        raise HTTPException(status_code=400, detail="Patient ID mismatch")
    db_immunization = Immunization(**immunization.dict())
    db.add(db_immunization)
    db.commit()
    db.refresh(db_immunization)
    return db_immunization

@router.get("/immunizations/{immunization_id}", response_model=ImmunizationSchema, dependencies=[Depends(RequirePermission("view_clinical"))])
def get_immunization(immunization_id: int, db: Session = Depends(get_db)):
    db_immunization = db.query(Immunization).filter(Immunization.id == immunization_id).first()
    if not db_immunization:
        raise HTTPException(status_code=404, detail="Immunization not found")
    return db_immunization
