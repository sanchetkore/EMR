"""Clinical Event Engine for building standardized longitudinal clinical timelines.
All deterministic SQL and rule-based queries - no LLM dependencies.
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.models.patient_brain import ClinicalEvent, PatientProblem
from app.models.encounter import Encounter
from app.models.lab_result import LabResult
from app.models.medication import Medication
from app.models.prescription import Prescription
from app.models.medical_problem import MedicalProblem
from app.schemas.patient_brain import ClinicalEventSchema


def record_clinical_event(
    db: Session,
    patient_id: int,
    event_type: str,
    event_date: datetime,
    title: str,
    summary: Optional[str] = None,
    source_type: Optional[str] = None,
    source_id: Optional[int] = None,
    metadata_json: Optional[Dict[str, Any]] = None,
) -> ClinicalEvent:
    """Record a single standardized event in the patient's clinical timeline."""
    event = ClinicalEvent(
        patient_id=patient_id,
        event_type=event_type,
        event_date=event_date,
        title=title,
        summary=summary,
        source_type=source_type,
        source_id=source_id,
        metadata_json=metadata_json,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def get_patient_timeline(
    db: Session,
    patient_id: int,
    limit: int = 100,
    event_type: Optional[str] = None,
) -> List[ClinicalEvent]:
    """Retrieve chronologically ordered standardized clinical events for a patient."""
    # First sync any unindexed historical records
    sync_historical_records_to_events(db, patient_id)

    query = db.query(ClinicalEvent).filter(ClinicalEvent.patient_id == patient_id)
    if event_type:
        query = query.filter(ClinicalEvent.event_type == event_type)

    return query.order_by(ClinicalEvent.event_date.desc(), ClinicalEvent.id.desc()).limit(limit).all()


def get_problem_timeline(
    db: Session,
    patient_id: int,
    problem_name_or_id: Any,
    limit: int = 50,
) -> List[ClinicalEvent]:
    """Retrieve longitudinal clinical events specifically relevant to a given problem."""
    sync_historical_records_to_events(db, patient_id)

    problem_name = ""
    if isinstance(problem_name_or_id, int):
        p = db.query(PatientProblem).filter(PatientProblem.id == problem_name_or_id).first()
        if p:
            problem_name = p.problem_name
    else:
        problem_name = str(problem_name_or_id)

    kw = f"%{problem_name.lower()}%" if problem_name else "%"

    events = (
        db.query(ClinicalEvent)
        .filter(
            ClinicalEvent.patient_id == patient_id,
            or_(
                ClinicalEvent.title.ilike(kw),
                ClinicalEvent.summary.ilike(kw),
            ),
        )
        .order_by(ClinicalEvent.event_date.desc(), ClinicalEvent.id.desc())
        .limit(limit)
        .all()
    )
    return events


def sync_historical_records_to_events(db: Session, patient_id: int):
    """Deterministically index historical encounters, labs, medications, and problems into clinical_events."""
    existing_events = (
        db.query(ClinicalEvent.source_type, ClinicalEvent.source_id)
        .filter(ClinicalEvent.patient_id == patient_id)
        .all()
    )
    existing_map = {(st, sid) for st, sid in existing_events if st and sid}

    new_events = []

    # 1. Sync Encounters / Visits
    encounters = db.query(Encounter).filter(Encounter.patient_id == patient_id).all()
    for enc in encounters:
        if ("encounter", enc.id) not in existing_map:
            complaint_texts = [c.complaint for c in enc.complaints if c.complaint]
            diagnosis_texts = [d.diagnosis for d in enc.diagnoses if d.diagnosis]
            summary_parts = []
            if enc.reason:
                summary_parts.append(f"Reason: {enc.reason}")
            if complaint_texts:
                summary_parts.append(f"Complaints: {', '.join(complaint_texts)}")
            if diagnosis_texts:
                summary_parts.append(f"Diagnoses: {', '.join(diagnosis_texts)}")

            new_events.append(
                ClinicalEvent(
                    patient_id=patient_id,
                    event_type="visit",
                    event_date=enc.encounter_date or enc.created_at or datetime.utcnow(),
                    title=f"Clinical Visit #{enc.id}",
                    summary=" | ".join(summary_parts) or "OPD Consultation completed",
                    source_type="encounter",
                    source_id=enc.id,
                    metadata_json={
                        "status": enc.status,
                        "diagnoses": diagnosis_texts,
                        "complaints": complaint_texts,
                    },
                )
            )
            existing_map.add(("encounter", enc.id))

    # 2. Sync Completed Labs
    labs = db.query(LabResult).filter(LabResult.patient_id == patient_id, LabResult.status == "Completed").all()
    for lab in labs:
        if ("lab_result", lab.id) not in existing_map:
            dt = lab.result_date or lab.ordered_date or datetime.utcnow()
            val_str = f"{lab.result_value} {lab.unit or ''}".strip()
            new_events.append(
                ClinicalEvent(
                    patient_id=patient_id,
                    event_type="lab",
                    event_date=dt,
                    title=f"Lab: {lab.test_name} - {val_str}",
                    summary=f"Result: {val_str}" + (f" (Ref: {lab.reference_range})" if lab.reference_range else ""),
                    source_type="lab_result",
                    source_id=lab.id,
                    metadata_json={
                        "test_name": lab.test_name,
                        "result_value": lab.result_value,
                        "unit": lab.unit,
                        "reference_range": lab.reference_range,
                    },
                )
            )
            existing_map.add(("lab_result", lab.id))

    # 3. Sync Medical Problems
    probs = db.query(MedicalProblem).filter(MedicalProblem.patient_id == patient_id).all()
    for p in probs:
        if ("medical_problem", p.id) not in existing_map:
            dt = datetime.combine(p.onset_date, datetime.min.time()) if p.onset_date else (p.created_at or datetime.utcnow())
            new_events.append(
                ClinicalEvent(
                    patient_id=patient_id,
                    event_type="diagnosis",
                    event_date=dt,
                    title=f"Diagnosed: {p.title}",
                    summary=f"Status: {p.status}" + (f", Notes: {p.notes}" if p.notes else ""),
                    source_type="medical_problem",
                    source_id=p.id,
                    metadata_json={"title": p.title, "status": p.status, "icd_code": p.icd_code},
                )
            )
            existing_map.add(("medical_problem", p.id))

            # Also ensure a corresponding record in patient_problems table
            existing_pp = db.query(PatientProblem).filter(
                PatientProblem.patient_id == patient_id,
                PatientProblem.problem_name.ilike(p.title),
            ).first()
            if not existing_pp:
                db.add(
                    PatientProblem(
                        patient_id=patient_id,
                        problem_name=p.title,
                        problem_code=p.icd_code,
                        status=p.status.lower() if p.status else "active",
                        diagnosed_at=dt,
                        source_record_id=f"medical_problem_{p.id}",
                    )
                )

    # 4. Sync Medications
    meds = db.query(Medication).filter(Medication.patient_id == patient_id).all()
    for m in meds:
        if ("medication", m.id) not in existing_map:
            dt = datetime.combine(m.start_date, datetime.min.time()) if m.start_date else (m.created_at or datetime.utcnow())
            dose_str = f"{m.dosage or ''} {m.frequency or ''}".strip()
            new_events.append(
                ClinicalEvent(
                    patient_id=patient_id,
                    event_type="medication",
                    event_date=dt,
                    title=f"Medication: {m.drug_name} {dose_str}".strip(),
                    summary=f"Started {m.drug_name} ({dose_str}) - Status: {m.status}",
                    source_type="medication",
                    source_id=m.id,
                    metadata_json={"drug_name": m.drug_name, "dosage": m.dosage, "frequency": m.frequency},
                )
            )
            existing_map.add(("medication", m.id))

    if new_events:
        db.add_all(new_events)
        db.commit()
