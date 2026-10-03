"""Prepare Patient Service.
Pre-visit briefing layer that synthesizes all pertinent clinical context in under 1 second.
Zero or very low LLM tokens required.
"""
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from app.models.patient import Patient, Appointment
from app.models.encounter import Encounter
from app.models.allergy import Allergy
from app.models.patient_brain import PatientProblem, MedicationEvent
from app.services.since_last_visit_service import get_changes_since_last_visit
from app.services.open_loops_engine import get_patient_open_loops
from app.services.attention_engine import get_patient_attention_items
from app.schemas.patient_brain import (
    PreparePatientResponse,
    PatientDemographicsBrief,
    MedicationReasonItem,
    PatientProblemSchema,
)


def get_prepared_patient_brief(db: Session, patient_id: int) -> PreparePatientResponse:
    """Compile the complete pre-visit preparation brief for the clinician."""
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise ValueError(f"Patient with ID {patient_id} not found")

    # Demographics & Age
    age = None
    if patient.dob:
        today = date.today()
        age = today.year - patient.dob.year - ((today.month, today.day) < (patient.dob.month, patient.dob.day))

    demographics = PatientDemographicsBrief(
        id=patient.id,
        name=f"{patient.first_name} {patient.last_name}".strip(),
        age=age,
        gender=patient.gender,
        opd_number=patient.opd_number,
        blood_group=patient.blood_group,
    )

    # Current or upcoming appointment reason
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    current_appt = (
        db.query(Appointment)
        .filter(Appointment.patient_id == patient_id, Appointment.status.in_(["Scheduled", "Confirmed", "In Progress"]))
        .order_by(Appointment.appointment_time.asc())
        .first()
    )
    reason_for_visit = None
    if current_appt and current_appt.consultation:
        reason_for_visit = current_appt.consultation.complaints or current_appt.consultation.history
    if not reason_for_visit:
        last_enc = (
            db.query(Encounter)
            .filter(Encounter.patient_id == patient_id)
            .order_by(Encounter.encounter_date.desc())
            .first()
        )
        if last_enc:
            reason_for_visit = last_enc.reason

    # Active Problems
    problems = (
        db.query(PatientProblem)
        .filter(PatientProblem.patient_id == patient_id, PatientProblem.status.in_(["active", "chronic"]))
        .all()
    )
    active_problems = [PatientProblemSchema.model_validate(p) for p in problems]

    # Allergies
    allergies = db.query(Allergy).filter(Allergy.patient_id == patient_id).all()
    allergy_list = [{"allergen": a.allergen, "severity": a.severity or "Moderate"} for a in allergies]

    # Since Last Visit Changes & Reports
    changes = get_changes_since_last_visit(db, patient_id)

    # Open Loops
    all_loops = get_patient_open_loops(db, patient_id)
    pending_loops = [l for l in all_loops if l.status == "pending" and not l.is_overdue]
    overdue_loops = [l for l in all_loops if l.is_overdue]

    # Last Visit Assessment & Plan
    last_plan: Dict[str, Any] = {}
    last_enc = (
        db.query(Encounter)
        .filter(Encounter.patient_id == patient_id)
        .order_by(Encounter.encounter_date.desc(), Encounter.id.desc())
        .first()
    )
    if last_enc:
        last_plan = {
            "visit_id": last_enc.id,
            "date": last_enc.encounter_date.strftime("%Y-%m-%d") if last_enc.encounter_date else None,
            "treatments": [t.treatment for t in last_enc.treatments if t.treatment],
            "advice": last_enc.advice,
            "prescriptions": [
                f"{p.molecule} ({[p.morning, p.afternoon, p.evening, p.night].count('1')} doses/day)"
                for pr in last_enc.prescriptions
                for p in pr.items
                if p.molecule
            ],
            "followup": f"{last_enc.followup_days} days" if last_enc.followup_days else None,
        }

    # Why previous medications changed
    med_events = (
        db.query(MedicationEvent)
        .filter(MedicationEvent.patient_id == patient_id)
        .order_by(MedicationEvent.created_at.desc())
        .limit(5)
        .all()
    )
    med_reasons = [
        MedicationReasonItem(
            drug_name=m.drug_name,
            action=m.action,
            old_dose=m.old_dose,
            new_dose=m.new_dose,
            reason=m.reason or "Clinical adjustment",
            details=m.reason_details,
            date=m.created_at.strftime("%Y-%m-%d"),
        )
        for m in med_events
        if m.reason
    ]

    # Attention Items
    att = get_patient_attention_items(db, patient_id)
    attention_list = att["needs_decision"] + att["needs_attention"]

    return PreparePatientResponse(
        patient=demographics,
        reason_for_visit=reason_for_visit,
        active_problems=active_problems,
        allergies=allergy_list,
        since_last_visit_changes=changes.important_metric_changes,
        new_completed_reports=changes.new_results,
        pending_loops=pending_loops,
        overdue_loops=overdue_loops,
        last_plan=last_plan,
        why_previous_medications_changed=med_reasons,
        attention_items=attention_list,
    )
