"""Doctor Attention Engine.
Surfaces actionable clinical priorities without generic notification noise.
Three distinct categories:
- Needs Decision: Active clinician intervention required (e.g. Creatinine jump)
- Needs Attention: Clinically notable (e.g. Overdue loop)
- FYI: Completed routine records
"""
from datetime import datetime, date, timedelta, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.models.patient import Patient, Appointment
from app.models.encounter import Encounter
from app.models.lab_result import LabResult
from app.models.patient_brain import OpenLoop, MedicationEvent, PatientProblem
from app.services.trend_engine import calculate_lab_trends, calculate_vital_trends
from app.services.open_loops_engine import get_patient_open_loops
from app.schemas.patient_brain import AttentionItem, AttentionQueueResponse


def get_patient_attention_items(db: Session, patient_id: int) -> Dict[str, List[Dict[str, Any]]]:
    """Retrieve actionable categorized attention items for a single patient."""
    needs_decision = []
    needs_attention = []
    fyi = []

    # 1. Check Lab Trends for critical worsening (Needs Decision)
    lab_trends = calculate_lab_trends(db, patient_id)
    for lt in lab_trends:
        name_lower = lt.metric_name.lower()
        if "creatinine" in name_lower and lt.delta is not None and lt.delta >= 0.3:
            needs_decision.append({
                "type": "lab_worsening",
                "title": f"{lt.metric_name} Increased",
                "detail": f"{lt.previous_display} -> {lt.latest_display} (+{lt.delta})",
                "source_type": "lab",
            })
        elif "hba1c" in name_lower and lt.delta is not None and lt.delta >= 0.5:
            needs_decision.append({
                "type": "glycemic_escalation",
                "title": f"HbA1c Elevated",
                "detail": f"{lt.previous_display} -> {lt.latest_display} (+{lt.delta}%)",
                "source_type": "lab",
            })
        elif lt.clinical_status in ("abnormal_high", "abnormal_low"):
            needs_attention.append({
                "type": "abnormal_lab",
                "title": f"{lt.metric_name} {lt.clinical_status.replace('_', ' ').capitalize()}",
                "detail": f"Latest: {lt.latest_display} (Ref: {lt.reference_range or 'N/A'})",
                "source_type": "lab",
            })

    # 2. Check Overdue Open Loops (Needs Attention)
    loops = get_patient_open_loops(db, patient_id)
    for l in loops:
        if l.is_overdue:
            needs_attention.append({
                "type": "overdue_loop",
                "title": f"{l.description} Overdue",
                "detail": f"{l.days_overdue} days overdue (Expected: {l.expected_date.strftime('%d %b %Y')})",
                "source_type": "open_loop",
                "source_id": l.id,
            })
        elif l.status == "completed" and l.completed_at:
            # Recent completions as FYI
            days_ago = (datetime.utcnow() - l.completed_at).days
            if days_ago <= 7:
                fyi.append({
                    "type": "completed_loop",
                    "title": f"{l.description} Completed",
                    "detail": l.completion_note or "Completed",
                    "source_type": "open_loop",
                    "source_id": l.id,
                })

    # 3. Check Recent Discontinued Medications with Adverse Effect (Needs Attention)
    stopped_meds = (
        db.query(MedicationEvent)
        .filter(
            MedicationEvent.patient_id == patient_id,
            MedicationEvent.action == "stopped",
        )
        .order_by(MedicationEvent.created_at.desc())
        .limit(3)
        .all()
    )
    for sm in stopped_meds:
        if sm.reason and "adverse" in sm.reason.lower():
            needs_attention.append({
                "type": "adverse_medication",
                "title": f"{sm.drug_name} Stopped Due to Adverse Effect",
                "detail": f"Reason: {sm.reason_details or sm.reason}",
                "source_type": "medication_event",
                "source_id": sm.id,
            })

    return {
        "needs_decision": needs_decision,
        "needs_attention": needs_attention,
        "fyi": fyi,
    }


def get_clinic_attention_queue(
    db: Session, doctor_id: Optional[int] = None, page: int = 1, page_size: int = 20,
) -> AttentionQueueResponse:
    """Scan one page of distinct active patients with appointments today (IST)."""
    if page < 1 or not 1 <= page_size <= 50:
        raise ValueError("Invalid attention queue pagination")
    today = datetime.now(timezone(timedelta(hours=5, minutes=30))).date()
    start = datetime.combine(today, datetime.min.time())
    appointments = db.query(Appointment.id).filter(
        Appointment.patient_id == Patient.id,
        Appointment.appointment_time >= start,
        Appointment.appointment_time < start + timedelta(days=1),
        Appointment.status.notin_(["Cancelled", "Canceled", "No Show", "no show"]),
    )
    if doctor_id is not None:
        appointments = appointments.filter(Appointment.doctor_id == doctor_id)
    patients_query = db.query(Patient).filter(Patient.is_active == 1, appointments.exists())
    total_patients = patients_query.count()
    patients = patients_query.order_by(Patient.id).offset((page - 1) * page_size).limit(page_size).all()

    decision_items: List[AttentionItem] = []
    attention_items: List[AttentionItem] = []
    fyi_items: List[AttentionItem] = []

    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M")

    for p in patients:
        p_name = f"{p.first_name} {p.last_name}".strip()
        att = get_patient_attention_items(db, p.id)

        for d in att["needs_decision"]:
            decision_items.append(
                AttentionItem(
                    patient_id=p.id,
                    patient_name=p_name,
                    opd_number=p.opd_number,
                    category="needs_decision",
                    title=d["title"],
                    detail=d["detail"],
                    source_type=d.get("source_type"),
                    source_id=d.get("source_id"),
                    created_at=now_str,
                )
            )

        for a in att["needs_attention"]:
            attention_items.append(
                AttentionItem(
                    patient_id=p.id,
                    patient_name=p_name,
                    opd_number=p.opd_number,
                    category="needs_attention",
                    title=a["title"],
                    detail=a["detail"],
                    source_type=a.get("source_type"),
                    source_id=a.get("source_id"),
                    created_at=now_str,
                )
            )

        for f in att["fyi"][:1]:
            fyi_items.append(
                AttentionItem(
                    patient_id=p.id,
                    patient_name=p_name,
                    opd_number=p.opd_number,
                    category="fyi",
                    title=f["title"],
                    detail=f["detail"],
                    source_type=f.get("source_type"),
                    source_id=f.get("source_id"),
                    created_at=now_str,
                )
            )

    total = len(decision_items) + len(attention_items) + len(fyi_items)
    return AttentionQueueResponse(
        needs_decision=decision_items,
        needs_attention=attention_items,
        fyi=fyi_items,
        total_count=total,
        page=page,
        page_size=page_size,
        total_patients=total_patients,
        scanned_patients=len(patients),
        has_next=page * page_size < total_patients,
        appointment_date=today,
    )
