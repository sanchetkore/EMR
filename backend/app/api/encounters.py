from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.database import get_db
from app.models.encounter import Encounter
from app.schemas.encounter import Encounter as EncounterSchema, EncounterCreate
from app.api.deps import RequirePermission

router = APIRouter()

@router.get("/", response_model=List[EncounterSchema], dependencies=[Depends(RequirePermission("view_clinical"))])
def get_encounters(patient_id: Optional[int] = None, doctor_id: Optional[int] = None, status: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Encounter)
    if patient_id:
        query = query.filter(Encounter.patient_id == patient_id)
    if doctor_id:
        query = query.filter(Encounter.doctor_id == doctor_id)
    if status:
        query = query.filter(Encounter.status == status)
    return query.all()

@router.post("/", response_model=EncounterSchema, dependencies=[Depends(RequirePermission("manage_clinical"))])
def create_encounter(encounter: EncounterCreate, db: Session = Depends(get_db)):
    db_encounter = Encounter(**encounter.dict())
    db.add(db_encounter)
    db.commit()
    db.refresh(db_encounter)
    return db_encounter

@router.get("/{encounter_id}", response_model=EncounterSchema, dependencies=[Depends(RequirePermission("view_clinical"))])
def get_encounter(encounter_id: int, db: Session = Depends(get_db)):
    db_encounter = db.query(Encounter).filter(Encounter.id == encounter_id).first()
    if not db_encounter:
        raise HTTPException(status_code=404, detail="Encounter not found")
    return db_encounter

@router.put("/{encounter_id}", response_model=EncounterSchema, dependencies=[Depends(RequirePermission("manage_clinical"))])
def update_encounter(encounter_id: int, encounter_update: EncounterCreate, db: Session = Depends(get_db)):
    db_encounter = db.query(Encounter).filter(Encounter.id == encounter_id).first()
    if not db_encounter:
        raise HTTPException(status_code=404, detail="Encounter not found")
    
    for var, value in encounter_update.model_dump(exclude_unset=True).items():
        setattr(db_encounter, var, value)
        
    db.commit()
    db.refresh(db_encounter)
    return db_encounter
