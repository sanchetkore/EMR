from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.models.insurance import Insurance
from app.schemas.insurance import Insurance as InsuranceSchema, InsuranceCreate
from app.api.deps import RequirePermission

router = APIRouter()

@router.get("/patients/{patient_id}/insurance", response_model=List[InsuranceSchema], dependencies=[Depends(RequirePermission("view_patients"))])
def get_patient_insurance(patient_id: int, db: Session = Depends(get_db)):
    return db.query(Insurance).filter(Insurance.patient_id == patient_id).all()

@router.post("/patients/{patient_id}/insurance", response_model=InsuranceSchema, dependencies=[Depends(RequirePermission("manage_patients"))])
def create_patient_insurance(patient_id: int, insurance: InsuranceCreate, db: Session = Depends(get_db)):
    if insurance.patient_id != patient_id:
        raise HTTPException(status_code=400, detail="Patient ID mismatch")
    db_insurance = Insurance(**insurance.dict())
    db.add(db_insurance)
    db.commit()
    db.refresh(db_insurance)
    return db_insurance

@router.put("/insurance/{insurance_id}", response_model=InsuranceSchema, dependencies=[Depends(RequirePermission("manage_patients"))])
def update_insurance(insurance_id: int, insurance_update: InsuranceCreate, db: Session = Depends(get_db)):
    db_insurance = db.query(Insurance).filter(Insurance.id == insurance_id).first()
    if not db_insurance:
        raise HTTPException(status_code=404, detail="Insurance not found")
    
    for var, value in vars(insurance_update).items():
        setattr(db_insurance, var, value)
        
    db.commit()
    db.refresh(db_insurance)
    return db_insurance
