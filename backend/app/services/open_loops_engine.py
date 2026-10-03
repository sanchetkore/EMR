"""Open Loops Engine for clinical expectations, outstanding actions, and auto-matching closure.
Zero LLM required - fully deterministic.
"""
from datetime import datetime, date
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.models.patient_brain import OpenLoop, ClinicalEvent
from app.schemas.patient_brain import OpenLoopSchema


def create_open_loop(
    db: Session,
    patient_id: int,
    loop_type: str,
    description: str,
    expected_date: Optional[date] = None,
    target_code: Optional[str] = None,
    problem_id: Optional[int] = None,
    source_visit_id: Optional[int] = None,
    source_order_id: Optional[int] = None,
) -> OpenLoop:
    """Create an open clinical loop representing an expected future action or result."""
    loop = OpenLoop(
        patient_id=patient_id,
        problem_id=problem_id,
        type=loop_type,
        description=description,
        target_code=target_code.upper() if target_code else None,
        expected_date=expected_date,
        status="pending",
        source_visit_id=source_visit_id,
        source_order_id=source_order_id,
    )
    db.add(loop)
    db.commit()
    db.refresh(loop)

    # Record event in timeline
    event = ClinicalEvent(
        patient_id=patient_id,
        event_type="loop_created",
        event_date=datetime.utcnow(),
        title=f"Pending: {description}",
        summary=f"Expected by: {expected_date.strftime('%Y-%m-%d') if expected_date else 'Soon'}",
        source_type="open_loop",
        source_id=loop.id,
        metadata_json={"type": loop_type, "target_code": target_code},
    )
    db.add(event)
    db.commit()

    return loop


def get_patient_open_loops(
    db: Session,
    patient_id: int,
    status_filter: Optional[str] = None,
) -> List[OpenLoopSchema]:
    """Retrieve open loops for a patient, dynamically evaluating overdue state."""
    query = db.query(OpenLoop).filter(OpenLoop.patient_id == patient_id)
    if status_filter:
        query = query.filter(OpenLoop.status == status_filter)

    loops = query.order_by(OpenLoop.expected_date.asc().nulls_last(), OpenLoop.id.desc()).all()
    today = date.today()

    result = []
    for l in loops:
        is_overdue = False
        days_overdue = 0
        current_status = l.status

        if l.status == "pending" and l.expected_date:
            if l.expected_date < today:
                is_overdue = True
                days_overdue = (today - l.expected_date).days
                current_status = "overdue"

        schema_obj = OpenLoopSchema(
            id=l.id,
            patient_id=l.patient_id,
            problem_id=l.problem_id,
            type=l.type,
            description=l.description,
            target_code=l.target_code,
            expected_date=l.expected_date,
            status=current_status,
            is_overdue=is_overdue,
            days_overdue=days_overdue,
            source_visit_id=l.source_visit_id,
            source_order_id=l.source_order_id,
            completed_at=l.completed_at,
            result_id=l.result_id,
            completion_note=l.completion_note,
            created_at=l.created_at,
        )
        result.append(schema_obj)

    return result


def match_open_loops(
    db: Session,
    patient_id: int,
    event_type: str,
    test_name_or_code: str,
    result_id: Optional[int] = None,
) -> List[OpenLoop]:
    """Automatically match and complete pending open loops when matching events arrive.
    No AI call is required.
    """
    if not test_name_or_code:
        return []

    token = test_name_or_code.strip().upper()

    # Query pending loops for this patient
    pending_loops = (
        db.query(OpenLoop)
        .filter(OpenLoop.patient_id == patient_id, OpenLoop.status == "pending")
        .all()
    )

    matched = []
    now = datetime.utcnow()

    for loop in pending_loops:
        is_match = False
        loop_target = (loop.target_code or "").strip().upper()
        loop_desc = loop.description.strip().upper()

        if loop_target and (loop_target in token or token in loop_target):
            is_match = True
        elif token in loop_desc:
            is_match = True
        else:
            # Check common medical synonyms (e.g. HbA1c <-> Glycated Hemoglobin, Creatinine <-> Serum Creatinine)
            synonyms = {
                "HBA1C": ["HBA1C", "GLYCATED", "HEMOGLOBIN A1C", "A1C"],
                "CREATININE": ["CREATININE", "SERUM CREATININE", "CREAT"],
                "CBC": ["CBC", "COMPLETE BLOOD COUNT", "HEMOGRAM"],
                "LIPID": ["LIPID", "CHOLESTEROL", "TRIGLYCERIDES"],
                "LFT": ["LFT", "LIVER FUNCTION", "SGOT", "SGPT", "BILIRUBIN"],
                "KFT": ["KFT", "RFT", "RENAL FUNCTION", "UREA", "BUN"],
                "BP": ["BP", "BLOOD PRESSURE"],
            }
            for key, syns in synonyms.items():
                if any(s in token for s in syns) and (key in loop_desc or any(s in loop_desc for s in syns)):
                    is_match = True
                    break

        if is_match:
            loop.status = "completed"
            loop.completed_at = now
            loop.result_id = result_id
            loop.completion_note = f"Auto-closed by received {event_type}: {test_name_or_code}"
            matched.append(loop)

            # Record event in timeline
            db.add(
                ClinicalEvent(
                    patient_id=patient_id,
                    event_type="loop_closed",
                    event_date=now,
                    title=f"Completed: {loop.description}",
                    summary=f"Matched with {test_name_or_code} (Result #{result_id or 'N/A'})",
                    source_type="open_loop",
                    source_id=loop.id,
                )
            )

    if matched:
        db.commit()
        for m in matched:
            db.refresh(m)

    return matched


def close_open_loop(
    db: Session,
    loop_id: int,
    completion_note: Optional[str] = None,
    result_id: Optional[int] = None,
) -> Optional[OpenLoop]:
    """Manually complete or dismiss an open loop."""
    loop = db.query(OpenLoop).filter(OpenLoop.id == loop_id).first()
    if not loop:
        return None

    now = datetime.utcnow()
    loop.status = "completed"
    loop.completed_at = now
    loop.result_id = result_id
    loop.completion_note = completion_note or "Closed by clinician"

    db.add(
        ClinicalEvent(
            patient_id=loop.patient_id,
            event_type="loop_closed",
            event_date=now,
            title=f"Completed: {loop.description}",
            summary=completion_note or "Closed by clinician",
            source_type="open_loop",
            source_id=loop.id,
        )
    )
    db.commit()
    db.refresh(loop)
    return loop
