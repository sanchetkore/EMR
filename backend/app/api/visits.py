from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from app.core.database import get_db
from app.models.encounter import Encounter, PatientVital, VisitComplaint, VisitDiagnosis, VisitTreatment, VitalConfiguration
from app.models.lab_result import LabResult, LabCatalog
from app.models.prescription import Prescription, PrescriptionItem
from app.schemas.encounter import VisitPayload, VisitResponse, VitalConfiguration as VitalConfigurationSchema, VitalConfigurationBase
from app.api.deps import RequirePermission

router = APIRouter()

@router.get("/vitals/config", response_model=List[VitalConfigurationSchema], dependencies=[Depends(RequirePermission("view_clinical"))])
def get_vital_configs(db: Session = Depends(get_db)):
    return db.query(VitalConfiguration).filter(VitalConfiguration.is_active == True).all()

@router.post("/vitals/config", response_model=VitalConfigurationSchema, dependencies=[Depends(RequirePermission("manage_clinical"))])
def create_vital_config(config: VitalConfigurationBase, db: Session = Depends(get_db)):
    db_config = VitalConfiguration(**config.dict())
    db.add(db_config)
    db.commit()
    db.refresh(db_config)
    return db_config

@router.get("/last/{patient_id}", response_model=VisitResponse, dependencies=[Depends(RequirePermission("view_clinical"))])
def get_last_visit(patient_id: int, db: Session = Depends(get_db)):
    # Find the most recent encounter for this patient
    encounter = db.query(Encounter).filter(Encounter.patient_id == patient_id).order_by(Encounter.encounter_date.desc()).first()
    
    if not encounter:
        raise HTTPException(status_code=404, detail="No previous visits found for this patient")
        
    return VisitResponse(
        encounter=encounter,
        vitals=encounter.vitals,
        complaints=encounter.complaints,
        diagnoses=encounter.diagnoses,
        treatments=encounter.treatments
    )

@router.get("/history/{patient_id}", response_model=List[VisitResponse], dependencies=[Depends(RequirePermission("view_clinical"))])
def get_visit_history(patient_id: int, limit: int = 6, db: Session = Depends(get_db)):
    # Find the most recent encounters for this patient, up to the limit (default 6)
    encounters = db.query(Encounter).filter(Encounter.patient_id == patient_id).order_by(Encounter.encounter_date.desc()).limit(limit).all()
    
    history = []
    for enc in encounters:
        history.append(VisitResponse(
            encounter=enc,
            vitals=enc.vitals,
            complaints=enc.complaints,
            diagnoses=enc.diagnoses,
            treatments=enc.treatments
        ))
    return history

@router.post("/", response_model=VisitResponse, dependencies=[Depends(RequirePermission("manage_clinical"))])
def create_visit(payload: VisitPayload, db: Session = Depends(get_db)):
    # 1. Create Encounter
    # Auto-calculate visit number
    previous_visits_count = db.query(Encounter).filter(Encounter.patient_id == payload.patient_id).count()
    visit_num = previous_visits_count + 1
    
    db_encounter = Encounter(
        patient_id=payload.patient_id,
        doctor_id=payload.doctor_id,
        appointment_id=payload.appointment_id,
        reason=payload.reason,
        notes=payload.notes,
        quick_notes=payload.quick_notes,
        advice=payload.advice,
        visit_number=visit_num,
        status=payload.status
    )
    db.add(db_encounter)
    db.flush() # flush to get the encounter id without committing the transaction yet
    
    # 2. Add Vitals
    for vital in payload.vitals:
        db_vital = PatientVital(
            encounter_id=db_encounter.id,
            vital_config_id=vital.vital_config_id,
            value=vital.value
        )
        db.add(db_vital)
        
    # 3. Add Complaints
    for complaint in payload.complaints:
        db_complaint = VisitComplaint(
            encounter_id=db_encounter.id,
            **complaint.dict()
        )
        db.add(db_complaint)
        
    # 4. Add Diagnoses
    for diagnosis in payload.diagnoses:
        db_diagnosis = VisitDiagnosis(
            encounter_id=db_encounter.id,
            **diagnosis.dict()
        )
        db.add(db_diagnosis)
        
    # 5. Add Treatments
    for treatment in payload.treatments:
        db_treatment = VisitTreatment(
            encounter_id=db_encounter.id,
            **treatment.dict()
        )
        db.add(db_treatment)
        
    # 6. Add Lab Orders (LabResult)
    for catalog_id in payload.lab_test_catalogs:
        catalog_item = db.query(LabCatalog).filter(LabCatalog.id == catalog_id).first()
        if catalog_item:
            db_lab = LabResult(
                patient_id=payload.patient_id,
                encounter_id=db_encounter.id,
                catalog_id=catalog_id,
                test_name=catalog_item.name,
                status="Pending",
                ordered_by=payload.doctor_id
            )
            db.add(db_lab)
            
    # 7. Add Prescriptions
    if payload.prescriptions:
        # Create a prescription record linked to the encounter/patient
        db_prescription = Prescription(
            patient_id=payload.patient_id,
            doctor_id=payload.doctor_id,
            appointment_id=payload.appointment_id,
            notes=f"Created during Visit #{visit_num}"
        )
        db.add(db_prescription)
        db.flush()
        
        for p_item in payload.prescriptions:
            db_p_item = PrescriptionItem(
                prescription_id=db_prescription.id,
                **p_item.dict()
            )
            db.add(db_p_item)

    # Commit all changes atomically
    db.commit()
    db.refresh(db_encounter)
    
    return VisitResponse(
        encounter=db_encounter,
        vitals=db_encounter.vitals,
        complaints=db_encounter.complaints,
        diagnoses=db_encounter.diagnoses,
        treatments=db_encounter.treatments
    )
