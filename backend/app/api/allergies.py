from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.database import get_db
from app.models.allergy import Allergy
from app.schemas.allergy import Allergy as AllergySchema, AllergyCreate
from app.api.deps import RequirePermission

router = APIRouter()

@router.get("/patients/{patient_id}/allergies", response_model=List[AllergySchema], dependencies=[Depends(RequirePermission("view_clinical"))])
def get_allergies(patient_id: int, db: Session = Depends(get_db)):
    return db.query(Allergy).filter(Allergy.patient_id == patient_id).all()

@router.post("/patients/{patient_id}/allergies", response_model=AllergySchema, dependencies=[Depends(RequirePermission("manage_clinical"))])
def create_allergy(patient_id: int, allergy: AllergyCreate, db: Session = Depends(get_db)):
    if allergy.patient_id != patient_id:
        raise HTTPException(status_code=400, detail="Patient ID mismatch")
    db_allergy = Allergy(**allergy.dict())
    db.add(db_allergy)
    db.commit()
    db.refresh(db_allergy)
    return db_allergy

@router.get("/allergies/{allergy_id}", response_model=AllergySchema, dependencies=[Depends(RequirePermission("view_clinical"))])
def get_allergy(allergy_id: int, db: Session = Depends(get_db)):
    db_allergy = db.query(Allergy).filter(Allergy.id == allergy_id).first()
    if not db_allergy:
        raise HTTPException(status_code=404, detail="Allergy not found")
    return db_allergy

@router.put("/allergies/{allergy_id}", response_model=AllergySchema, dependencies=[Depends(RequirePermission("manage_clinical"))])
def update_allergy(allergy_id: int, allergy_update: AllergyCreate, db: Session = Depends(get_db)):
    db_allergy = db.query(Allergy).filter(Allergy.id == allergy_id).first()
    if not db_allergy:
        raise HTTPException(status_code=404, detail="Allergy not found")
    
    for var, value in allergy_update.model_dump(exclude_unset=True).items():
        setattr(db_allergy, var, value)
        
    db.commit()
    db.refresh(db_allergy)
    return db_allergy

@router.delete("/allergies/{allergy_id}", dependencies=[Depends(RequirePermission("manage_clinical"))])
def delete_allergy(allergy_id: int, db: Session = Depends(get_db)):
    db_allergy = db.query(Allergy).filter(Allergy.id == allergy_id).first()
    if not db_allergy:
        raise HTTPException(status_code=404, detail="Allergy not found")
    db.delete(db_allergy)
    db.commit()
    return {"detail": "Allergy deleted successfully"}
