from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.database import get_db
from app.models.medical_problem import MedicalProblem
from app.schemas.medical_problem import MedicalProblem as MedicalProblemSchema, MedicalProblemCreate
from app.api.deps import RequirePermission

router = APIRouter()

@router.get("/patients/{patient_id}/medical_problems", response_model=List[MedicalProblemSchema], dependencies=[Depends(RequirePermission("view_clinical"))])
def get_medical_problems(patient_id: int, db: Session = Depends(get_db)):
    return db.query(MedicalProblem).filter(MedicalProblem.patient_id == patient_id).all()

@router.post("/patients/{patient_id}/medical_problems", response_model=MedicalProblemSchema, dependencies=[Depends(RequirePermission("manage_clinical"))])
def create_medical_problem(patient_id: int, problem: MedicalProblemCreate, db: Session = Depends(get_db)):
    if problem.patient_id != patient_id:
        raise HTTPException(status_code=400, detail="Patient ID mismatch")
    db_problem = MedicalProblem(**problem.dict())
    db.add(db_problem)
    db.commit()
    db.refresh(db_problem)
    return db_problem

@router.get("/medical_problems/{problem_id}", response_model=MedicalProblemSchema, dependencies=[Depends(RequirePermission("view_clinical"))])
def get_medical_problem(problem_id: int, db: Session = Depends(get_db)):
    db_problem = db.query(MedicalProblem).filter(MedicalProblem.id == problem_id).first()
    if not db_problem:
        raise HTTPException(status_code=404, detail="Medical Problem not found")
    return db_problem

@router.put("/medical_problems/{problem_id}", response_model=MedicalProblemSchema, dependencies=[Depends(RequirePermission("manage_clinical"))])
def update_medical_problem(problem_id: int, problem_update: MedicalProblemCreate, db: Session = Depends(get_db)):
    db_problem = db.query(MedicalProblem).filter(MedicalProblem.id == problem_id).first()
    if not db_problem:
        raise HTTPException(status_code=404, detail="Medical Problem not found")
    
    for var, value in problem_update.model_dump(exclude_unset=True).items():
        setattr(db_problem, var, value)
        
    db.commit()
    db.refresh(db_problem)
    return db_problem
