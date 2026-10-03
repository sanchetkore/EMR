"""'Why?' Clinical Memory Service.
Captures and retrieves structured clinical rationales for medication changes and medical decisions.
Enables instant contextual intelligence and answers 'Why was X stopped/changed?' deterministically.
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.models.patient_brain import MedicationEvent, ClinicalDecision, ClinicalEvent
from app.schemas.patient_brain import MedicationEventSchema, ClinicalDecisionSchema, MedicationReasonItem


def record_medication_event(
    db: Session,
    patient_id: int,
    drug_name: str,
    action: str,
    old_dose: Optional[str] = None,
    new_dose: Optional[str] = None,
    reason: Optional[str] = None,
    reason_details: Optional[str] = None,
    medication_id: Optional[int] = None,
    visit_id: Optional[int] = None,
    doctor_id: Optional[int] = None,
) -> MedicationEvent:
    """Record a structured medication event with clear clinical reason."""
    now = datetime.utcnow()
    event = MedicationEvent(
        patient_id=patient_id,
        medication_id=medication_id,
        drug_name=drug_name.strip(),
        action=action,
        old_dose=old_dose,
        new_dose=new_dose,
        reason=reason,
        reason_details=reason_details,
        visit_id=visit_id,
        doctor_id=doctor_id,
        created_at=now,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    # Add to clinical timeline
    dose_change = ""
    if old_dose and new_dose:
        dose_change = f" ({old_dose} -> {new_dose})"
    elif new_dose:
        dose_change = f" ({new_dose})"

    action_label = {
        "started": f"Started {drug_name}{dose_change}",
        "stopped": f"Stopped {drug_name}",
        "dose_increased": f"Increased {drug_name}{dose_change}",
        "dose_decreased": f"Decreased {drug_name}{dose_change}",
        "switched": f"Switched {drug_name}",
    }.get(action, f"{action.capitalize()} {drug_name}")

    summary_text = action_label
    if reason:
        summary_text += f" | WHY: {reason}"
        if reason_details:
            summary_text += f" ({reason_details})"

    timeline_event = ClinicalEvent(
        patient_id=patient_id,
        event_type="medication",
        event_date=now,
        title=action_label,
        summary=summary_text,
        source_type="medication_event",
        source_id=event.id,
        metadata_json={
            "drug_name": drug_name,
            "action": action,
            "old_dose": old_dose,
            "new_dose": new_dose,
            "reason": reason,
            "reason_details": reason_details,
        },
    )
    db.add(timeline_event)
    db.commit()

    return event


def record_clinical_decision(
    db: Session,
    patient_id: int,
    decision: str,
    reason: Optional[str] = None,
    details: Optional[str] = None,
    problem_id: Optional[int] = None,
    doctor_id: Optional[int] = None,
    visit_id: Optional[int] = None,
) -> ClinicalDecision:
    """Record a clinical decision along with the rationale."""
    now = datetime.utcnow()
    cd = ClinicalDecision(
        patient_id=patient_id,
        problem_id=problem_id,
        decision=decision,
        reason=reason,
        details=details,
        doctor_id=doctor_id,
        visit_id=visit_id,
        created_at=now,
    )
    db.add(cd)
    db.commit()
    db.refresh(cd)

    # Timeline event
    db.add(
        ClinicalEvent(
            patient_id=patient_id,
            event_type="decision",
            event_date=now,
            title=f"Decision: {decision}",
            summary=f"Reason: {reason or 'Clinical judgement'}" + (f" - {details}" if details else ""),
            source_type="clinical_decision",
            source_id=cd.id,
            metadata_json={"decision": decision, "reason": reason, "details": details},
        )
    )
    db.commit()

    return cd


def get_medication_intelligence(
    db: Session,
    patient_id: int,
    drug_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Retrieve comprehensive longitudinal intelligence for a specific drug or all drugs for this patient."""
    query = db.query(MedicationEvent).filter(MedicationEvent.patient_id == patient_id)
    if drug_name:
        query = query.filter(MedicationEvent.drug_name.ilike(f"%{drug_name.strip()}%"))

    events = query.order_by(MedicationEvent.created_at.asc()).all()

    # Group by drug name
    grouped: Dict[str, List[MedicationEvent]] = {}
    for ev in events:
        d_name = ev.drug_name.strip()
        grouped.setdefault(d_name, []).append(ev)

    results = []
    for d_name, ev_list in grouped.items():
        started_event = next((e for e in ev_list if e.action == "started"), ev_list[0])
        stopped_event = next((e for e in reversed(ev_list) if e.action == "stopped"), None)
        latest_event = ev_list[-1]

        history_items = []
        for e in ev_list:
            history_items.append({
                "date": e.created_at.strftime("%Y-%m-%d"),
                "action": e.action,
                "transition": f"{e.old_dose} -> {e.new_dose}" if (e.old_dose and e.new_dose) else (e.new_dose or e.old_dose or ""),
                "reason": e.reason or "",
                "details": e.reason_details or "",
            })

        results.append({
            "drug_name": d_name,
            "started_at": started_event.created_at.strftime("%Y-%m-%d"),
            "status": "Stopped" if stopped_event else "Active",
            "stopped_at": stopped_event.created_at.strftime("%Y-%m-%d") if stopped_event else None,
            "stop_reason": stopped_event.reason if stopped_event else None,
            "stop_details": stopped_event.reason_details if stopped_event else None,
            "latest_dose": latest_event.new_dose or latest_event.old_dose,
            "last_changed": latest_event.created_at.strftime("%Y-%m-%d"),
            "change_count": len(ev_list),
            "history": history_items,
        })

    return {
        "patient_id": patient_id,
        "medications": results,
    }
