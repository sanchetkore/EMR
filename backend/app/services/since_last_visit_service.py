"""Since Last Visit Service.
Calculates all clinical deltas and new items that transpired since the previous visit.
Zero LLM tokens required.
"""
from datetime import datetime, date
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.models.encounter import Encounter
from app.models.lab_result import LabResult
from app.models.patient_brain import MedicationEvent, OpenLoop, ClinicalEvent
from app.models.document import Document
from app.services.trend_engine import calculate_lab_trends, calculate_vital_trends
from app.services.open_loops_engine import get_patient_open_loops
from app.schemas.patient_brain import ChangesSinceLastVisitResponse, MetricChangeItem, MedicationEventSchema


def get_changes_since_last_visit(db: Session, patient_id: int) -> ChangesSinceLastVisitResponse:
    """Gather all deterministic clinical events and metric differences since the previous consultation."""
    # Find encounters sorted descending
    encounters = (
        db.query(Encounter)
        .filter(Encounter.patient_id == patient_id)
        .order_by(Encounter.encounter_date.desc(), Encounter.id.desc())
        .all()
    )

    last_visit_date: Optional[datetime] = None
    days_since: Optional[int] = None

    if encounters:
        latest = encounters[0]
        last_visit_date = latest.encounter_date or latest.created_at
        if last_visit_date:
            days_since = (datetime.utcnow() - last_visit_date).days

    # Reference threshold for "new" events:
    # If there are 2 or more encounters, compare against previous encounter date;
    # If 1 encounter, everything resulted since that encounter date;
    # If 0 encounters, everything is new.
    cutoff_date = last_visit_date if last_visit_date else datetime(2000, 1, 1)

    # 1. New Completed Lab Results
    new_labs_query = (
        db.query(LabResult)
        .filter(
            LabResult.patient_id == patient_id,
            LabResult.status == "Completed",
            LabResult.result_date >= cutoff_date,
        )
        .order_by(LabResult.result_date.desc())
        .all()
    )
    new_results = [
        {
            "id": l.id,
            "test_name": l.test_name,
            "result_value": l.result_value,
            "unit": l.unit,
            "reference_range": l.reference_range,
            "result_date": l.result_date.strftime("%Y-%m-%d %H:%M") if l.result_date else None,
        }
        for l in new_labs_query
    ]

    # 2. Medication changes recorded at or since last visit
    med_events = (
        db.query(MedicationEvent)
        .filter(MedicationEvent.patient_id == patient_id, MedicationEvent.created_at >= cutoff_date)
        .order_by(MedicationEvent.created_at.desc())
        .all()
    )
    medication_changes = [MedicationEventSchema.model_validate(m) for m in med_events]

    # 3. New Diagnoses
    new_diagnoses: List[str] = []
    if encounters:
        for diag in encounters[0].diagnoses:
            if diag.diagnosis:
                new_diagnoses.append(diag.diagnosis)

    # 4. Completed & Pending Orders / Open Loops
    all_loops = get_patient_open_loops(db, patient_id)
    pending_orders = [l for l in all_loops if l.status in ("pending", "overdue")]
    completed_orders = [
        {
            "id": l.id,
            "description": l.description,
            "completed_at": l.completed_at.strftime("%Y-%m-%d") if l.completed_at else None,
            "note": l.completion_note,
        }
        for l in all_loops
        if l.status == "completed" and l.completed_at and l.completed_at >= cutoff_date
    ]

    # 5. New Documents
    docs = (
        db.query(Document)
        .filter(Document.patient_id == patient_id, Document.created_at >= cutoff_date)
        .all()
    )
    new_documents = [
        {"id": d.id, "title": d.title, "document_type": d.document_type, "date": d.created_at.strftime("%Y-%m-%d")}
        for d in docs
    ]

    # 6. Important Metric Changes (from Trend Engine)
    metric_changes: List[MetricChangeItem] = []
    lab_trends = calculate_lab_trends(db, patient_id)
    for lt in lab_trends:
        if lt.previous_display is not None and lt.latest_display != lt.previous_display:
            severity = "neutral"
            if lt.direction == "increased":
                # For creatinine / HbA1c increase is worse
                severity = "worse" if any(k in lt.metric_name.lower() for k in ["creatinine", "hba1c", "sugar", "glucose"]) else "neutral"
            elif lt.direction == "decreased":
                severity = "better" if any(k in lt.metric_name.lower() for k in ["creatinine", "hba1c", "sugar", "glucose"]) else "neutral"

            metric_changes.append(
                MetricChangeItem(
                    test_or_vital=lt.metric_name,
                    previous=lt.previous_display,
                    current=lt.latest_display,
                    delta=f"{lt.delta:+}" if lt.delta is not None else None,
                    direction=lt.direction,
                    severity=severity,
                )
            )

    vital_trends = calculate_vital_trends(db, patient_id)
    for vt in vital_trends:
        if vt.previous_display is not None and vt.latest_display != vt.previous_display:
            metric_changes.append(
                MetricChangeItem(
                    test_or_vital=vt.metric_name,
                    previous=vt.previous_display,
                    current=vt.latest_display,
                    delta=f"{vt.delta:+}" if vt.delta is not None else None,
                    direction=vt.direction,
                    severity="worse" if vt.clinical_status == "abnormal_high" else "neutral",
                )
            )

    return ChangesSinceLastVisitResponse(
        patient_id=patient_id,
        last_visit_date=last_visit_date.strftime("%Y-%m-%d") if last_visit_date else None,
        days_since_last_visit=days_since,
        new_results=new_results,
        medication_changes=medication_changes,
        new_diagnoses=new_diagnoses,
        completed_orders=completed_orders,
        pending_orders=pending_orders,
        new_documents=new_documents,
        new_referrals=[],
        important_metric_changes=metric_changes,
    )
