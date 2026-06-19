from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc
from typing import List, Optional
from app.core.database import get_db
from app.models.patient import Patient, Appointment
from app.models.prescription import Prescription
from app.schemas.patient import (
    Patient as PatientSchema, 
    PatientCreate, 
    Appointment as AppointmentSchema,
    PatientAISummarySchema
)
from app.api.deps import RequirePermission
from app.schemas.prescription import Prescription as PrescriptionSchema

router = APIRouter()

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
    db.flush()
    
    # Create initial "First Time" summary
    from app.models.patient import PatientAISummary
    db_summary = PatientAISummary(patient_id=db_patient.id, summary_text="First Time")
    db.add(db_summary)
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
    
    for var, value in patient_update.model_dump(exclude_unset=True).items():
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

@router.get("/{patient_id}/prescriptions", response_model=List[PrescriptionSchema], dependencies=[Depends(RequirePermission("view_clinical"))])
def get_patient_prescriptions(patient_id: int, db: Session = Depends(get_db)):
    db_patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not db_patient:
        raise HTTPException(status_code=404, detail="Patient not found")
        
    prescriptions = db.query(Prescription).filter(Prescription.patient_id == patient_id).order_by(Prescription.date_prescribed.desc()).all()
    return prescriptions

@router.get("/{patient_id}/ai_summary", response_model=Optional[PatientAISummarySchema], dependencies=[Depends(RequirePermission("view_patients"))])
def get_patient_ai_summary(patient_id: int, db: Session = Depends(get_db)):
    db_patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not db_patient:
        raise HTTPException(status_code=404, detail="Patient not found")
        
    from app.models.patient import PatientAISummary
    summary = db.query(PatientAISummary).filter(PatientAISummary.patient_id == patient_id).first()
    return summary

# --- Medical History: Allergies ---
from app.models.allergy import Allergy
from app.models.medical_problem import MedicalProblem
from app.schemas.allergy import Allergy as AllergySchema, AllergyCreate
from app.schemas.medical_problem import MedicalProblem as ConditionSchema, MedicalProblemCreate as ConditionCreate

@router.get("/{patient_id}/allergies", response_model=List[AllergySchema], dependencies=[Depends(RequirePermission("view_clinical"))])
def get_patient_allergies(patient_id: int, db: Session = Depends(get_db)):
    return db.query(Allergy).filter(Allergy.patient_id == patient_id).all()

@router.post("/{patient_id}/allergies", response_model=AllergySchema, dependencies=[Depends(RequirePermission("manage_clinical"))])
def create_patient_allergy(patient_id: int, allergy: AllergyCreate, db: Session = Depends(get_db)):
    if allergy.patient_id != patient_id:
        raise HTTPException(status_code=400, detail="Patient ID mismatch")
    db_allergy = Allergy(**allergy.dict())
    db.add(db_allergy)
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

# --- Medical History: Conditions (Medical Problems) ---

@router.get("/{patient_id}/conditions", response_model=List[ConditionSchema], dependencies=[Depends(RequirePermission("view_clinical"))])
def get_patient_conditions(patient_id: int, db: Session = Depends(get_db)):
    return db.query(MedicalProblem).filter(MedicalProblem.patient_id == patient_id).all()

@router.post("/{patient_id}/conditions", response_model=ConditionSchema, dependencies=[Depends(RequirePermission("manage_clinical"))])
def create_patient_condition(patient_id: int, condition: ConditionCreate, db: Session = Depends(get_db)):
    if condition.patient_id != patient_id:
        raise HTTPException(status_code=400, detail="Patient ID mismatch")
    db_condition = MedicalProblem(**condition.dict())
    db.add(db_condition)
    db.commit()
    db.refresh(db_condition)
    return db_condition

@router.delete("/conditions/{condition_id}", dependencies=[Depends(RequirePermission("manage_clinical"))])
def delete_condition(condition_id: int, db: Session = Depends(get_db)):
    db_condition = db.query(MedicalProblem).filter(MedicalProblem.id == condition_id).first()
    if not db_condition:
        raise HTTPException(status_code=404, detail="Condition not found")
    db.delete(db_condition)
    db.commit()
    return {"detail": "Condition deleted successfully"}
