"""Patient Brain Service.
Core coordinator maintaining the persistent structured clinical memory index for each patient.
"""
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from app.models.patient import Patient
from app.models.encounter import Encounter
from app.models.medication import Medication
from app.models.patient_brain import (
    PatientProblem,
    BrainSnapshot,
    BrainCorrection,
    MedicationEvent,
)
from app.services.trend_engine import calculate_lab_trends, calculate_vital_trends
from app.services.clinical_event_engine import sync_historical_records_to_events
from app.services.open_loops_engine import get_patient_open_loops
from app.services.attention_engine import get_patient_attention_items
from app.services.since_last_visit_service import get_changes_since_last_visit
from app.schemas.patient_brain import (
    PatientBrainResponse,
    PatientBrainProblemView,
    DoctorCorrectionResponse,
)


def get_or_build_patient_brain(db: Session, patient_id: int, force_refresh: bool = False) -> PatientBrainResponse:
    """Retrieve or compute the structured Patient Brain index."""
    # Ensure baseline historical events are synchronized
    sync_historical_records_to_events(db, patient_id)

    # Check for latest snapshot if not forcing refresh
    latest_snapshot = (
        db.query(BrainSnapshot)
        .filter(BrainSnapshot.patient_id == patient_id)
        .order_by(BrainSnapshot.version.desc())
        .first()
    )

    if latest_snapshot and not force_refresh:
        # Check if snapshot is less than 30 minutes old
        age = (datetime.utcnow() - latest_snapshot.generated_at).total_seconds()
        if age < 1800:
            return PatientBrainResponse(**latest_snapshot.snapshot_json)

    # Compute fresh brain state
    new_version = (latest_snapshot.version + 1) if latest_snapshot else 1

    # Active problems
    problems = (
        db.query(PatientProblem)
        .filter(PatientProblem.patient_id == patient_id)
        .order_by(PatientProblem.priority.desc(), PatientProblem.id.asc())
        .all()
    )

    # Trends
    lab_trends = calculate_lab_trends(db, patient_id)
    vital_trends = calculate_vital_trends(db, patient_id)

    # Open loops
    loops = get_patient_open_loops(db, patient_id)
    pending_loops = [l for l in loops if l.status == "pending" and not l.is_overdue]
    overdue_loops = [l for l in loops if l.is_overdue]

    # Attention items
    att = get_patient_attention_items(db, patient_id)

    # Active medications
    active_meds = (
        db.query(Medication)
        .filter(Medication.patient_id == patient_id, Medication.status == "Active")
        .all()
    )
    med_list = [
        {"id": m.id, "drug_name": m.drug_name, "dosage": m.dosage, "frequency": m.frequency}
        for m in active_meds
    ]

    # Changes since last visit count
    changes = get_changes_since_last_visit(db, patient_id)
    recent_changes_count = len(changes.important_metric_changes) + len(changes.new_results) + len(changes.medication_changes)

    # Build problem-specific views
    problem_views = []
    for p in problems:
        p_name = p.problem_name.lower()
        # Find relevant metrics for this problem (e.g. HbA1c / glucose for diabetes; BP for hypertension)
        relevant_metrics: Dict[str, Any] = {}
        relevant_trends: Dict[str, Any] = {}

        for lt in lab_trends:
            if any(term in lt.metric_name.lower() for term in [p_name, "glucose", "hba1c", "creatinine", "lipid"]):
                relevant_metrics[lt.metric_name] = lt.latest_display
                relevant_trends[lt.metric_name] = [pt.value for pt in lt.history]

        for vt in vital_trends:
            if "hyper" in p_name and "pressure" in vt.metric_name.lower():
                relevant_metrics["BP"] = vt.latest_display
                relevant_trends["BP"] = [pt.value for pt in vt.history]

        # Relevant medications
        prob_meds = [m["drug_name"] for m in med_list]

        # Pending items for this problem
        pending_items = [l.description for l in pending_loops if (l.problem_id == p.id or p_name in l.description.lower())]

        problem_views.append(
            PatientBrainProblemView(
                id=p.id,
                name=p.problem_name,
                status=p.status,
                diagnosed_at=p.diagnosed_at.strftime("%Y-%m-%d") if p.diagnosed_at else None,
                medications=prob_meds,
                latest_metrics=relevant_metrics,
                trends=relevant_trends,
                last_plan=None,
                pending=pending_items,
            )
        )

    # Latest vitals dictionary
    vitals_dict = {vt.metric_name: vt.latest_display for vt in vital_trends}

    brain_response = PatientBrainResponse(
        patient_id=patient_id,
        version=new_version,
        generated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        active_problems_count=len([p for p in problems if p.status in ("active", "chronic")]),
        open_loops_count=len(pending_loops),
        overdue_loops_count=len(overdue_loops),
        recent_changes_count=recent_changes_count,
        problems=problem_views,
        needs_attention=att["needs_attention"],
        needs_decision=att["needs_decision"],
        fyi=att["fyi"],
        open_loops=loops,
        active_medications=med_list,
        latest_vitals=vitals_dict,
    )

    # Persist snapshot
    snapshot = BrainSnapshot(
        patient_id=patient_id,
        version=new_version,
        generated_at=datetime.utcnow(),
        snapshot_json=brain_response.model_dump(),
    )
    db.add(snapshot)
    db.commit()

    return brain_response


def record_brain_correction(
    db: Session,
    patient_id: int,
    doctor_id: Optional[int],
    entity_type: str,
    entity_id: Optional[int],
    source_value: Optional[str],
    derived_value: Optional[str],
    doctor_correction: str,
) -> BrainCorrection:
    """Record a clinician's override or correction on derived brain state."""
    correction = BrainCorrection(
        patient_id=patient_id,
        doctor_id=doctor_id,
        entity_type=entity_type,
        entity_id=entity_id,
        source_value=source_value,
        derived_value=derived_value,
        doctor_correction=doctor_correction,
        corrected_at=datetime.utcnow(),
    )
    db.add(correction)
    db.commit()
    db.refresh(correction)

    # Force rebuild snapshot with correction applied
    get_or_build_patient_brain(db, patient_id, force_refresh=True)

    return correction
