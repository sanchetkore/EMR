from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.database import get_db
from app.models.drug import Drug
from app.schemas.drug import Drug as DrugSchema, DrugCreate
from app.api.deps import RequirePermission

router = APIRouter()

@router.get("/", response_model=List[DrugSchema], dependencies=[Depends(RequirePermission("view_clinical"))])
def get_drugs(search: Optional[str] = None, limit: int = 50, db: Session = Depends(get_db)):
    query = db.query(Drug).filter(Drug.is_active == True)
    if search:
        query = query.filter(Drug.name.ilike(f"%{search}%") | Drug.generic_name.ilike(f"%{search}%"))
    return query.limit(limit).all()

@router.post("/", response_model=DrugSchema, dependencies=[Depends(RequirePermission("manage_clinical"))])
def create_drug(drug: DrugCreate, db: Session = Depends(get_db)):
    db_drug = Drug(**drug.dict())
    db.add(db_drug)
    db.commit()
    db.refresh(db_drug)
    return db_drug

@router.get("/{drug_id}", response_model=DrugSchema, dependencies=[Depends(RequirePermission("view_clinical"))])
def get_drug(drug_id: int, db: Session = Depends(get_db)):
    db_drug = db.query(Drug).filter(Drug.id == drug_id).first()
    if not db_drug:
        raise HTTPException(status_code=404, detail="Drug not found")
    return db_drug

@router.put("/{drug_id}", response_model=DrugSchema, dependencies=[Depends(RequirePermission("manage_clinical"))])
def update_drug(drug_id: int, drug_update: DrugCreate, db: Session = Depends(get_db)):
    db_drug = db.query(Drug).filter(Drug.id == drug_id).first()
    if not db_drug:
        raise HTTPException(status_code=404, detail="Drug not found")
        
    for var, value in drug_update.model_dump(exclude_unset=True).items():
        setattr(db_drug, var, value)
        
    db.commit()
    db.refresh(db_drug)
    return db_drug
