from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from app.core.database import get_db
from app.models.lab_result import LabResult
from app.schemas.lab_result import LabResult as LabResultSchema, LabResultCreate
from app.api.deps import RequirePermission

router = APIRouter()

@router.get("/patients/{patient_id}/lab_results", response_model=List[LabResultSchema], dependencies=[Depends(RequirePermission("view_clinical"))])
def get_lab_results(patient_id: int, db: Session = Depends(get_db)):
    return db.query(LabResult).filter(LabResult.patient_id == patient_id).all()

@router.post("/lab_results", response_model=LabResultSchema, dependencies=[Depends(RequirePermission("manage_clinical"))])
def create_lab_result(lab_result: LabResultCreate, db: Session = Depends(get_db)):
    db_lab = LabResult(**lab_result.dict())
    db.add(db_lab)
    db.commit()
    db.refresh(db_lab)
    return db_lab

@router.get("/lab_results/{lab_id}", response_model=LabResultSchema, dependencies=[Depends(RequirePermission("view_clinical"))])
def get_lab_result(lab_id: int, db: Session = Depends(get_db)):
    db_lab = db.query(LabResult).filter(LabResult.id == lab_id).first()
    if not db_lab:
        raise HTTPException(status_code=404, detail="Lab Result not found")
    return db_lab

@router.put("/lab_results/{lab_id}", response_model=LabResultSchema, dependencies=[Depends(RequirePermission("manage_clinical"))])
def update_lab_result(lab_id: int, lab_update: LabResultCreate, db: Session = Depends(get_db)):
    db_lab = db.query(LabResult).filter(LabResult.id == lab_id).first()
    if not db_lab:
        raise HTTPException(status_code=404, detail="Lab Result not found")
    
    for var, value in vars(lab_update).items():
        setattr(db_lab, var, value)
        
    if lab_update.status == "Completed" and not db_lab.result_date:
        db_lab.result_date = datetime.utcnow()
        
    db.commit()
    db.refresh(db_lab)
    return db_lab
