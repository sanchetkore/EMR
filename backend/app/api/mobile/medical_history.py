from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy import or_
from app.core.database import get_db
from app.models.patient import Patient
from app.models.encounter import Encounter
from app.models.prescription import Prescription
from app.models.allergy import Allergy
from app.models.immunization import Immunization
from app.api.mobile.deps import get_current_patient

router = APIRouter(prefix="/medical-history", tags=["mobile-medical-history"])

@router.get("/")
def get_medical_history(
    current_patient: Patient = Depends(get_current_patient),
    db: Session = Depends(get_db)
):
    history_items = []

    # 1. Encounters / Clinical visits
    encounters = db.query(Encounter).options(
        joinedload(Encounter.doctor),
        selectinload(Encounter.complaints),
        selectinload(Encounter.diagnoses)
    ).filter(
        Encounter.patient_id == current_patient.id,
        Encounter.status == "Completed"
    ).order_by(Encounter.encounter_date.desc()).all()

    for enc in encounters:
        doc_name = f"Dr. {enc.doctor.username.capitalize()}" if enc.doctor else "Dr. Physician"
        date_str = enc.encounter_date.strftime("%b %d, %Y")

        complaint_texts = [c.complaint for c in enc.complaints if c.complaint]
        diag_texts = [d.diagnosis for d in enc.diagnoses if d.diagnosis]

        # Add Visit Note
        notes = enc.advice or enc.notes or enc.quick_notes or "No clinical note recorded."
        history_items.append({
            "id": f"ENC-{enc.id}",
            "recordType": "VISIT_NOTE",
            "title": f"Consultation Review • {', '.join(complaint_texts) if complaint_texts else 'Consultation'}",
            "subtitle": f"{doc_name} • Clinical Encounter",
            "doctorName": doc_name,
            "dateLabel": date_str,
            "details": notes,
            "badgeLabel": "Doctor Note"
        })

        # Add Diagnoses
        for idx, diag in enumerate(diag_texts):
            history_items.append({
                "id": f"DIAG-{enc.id}-{idx}",
                "recordType": "DIAGNOSIS",
                "title": f"Clinical Diagnosis: {diag}",
                "subtitle": f"Diagnosed by {doc_name}",
                "doctorName": doc_name,
                "dateLabel": date_str,
                "details": f"Formal diagnostic assessment entered during clinical visit on {date_str}.",
                "badgeLabel": "Diagnosis"
            })

    # 2. Prescriptions
    prescriptions = db.query(Prescription).outerjoin(Encounter, Prescription.encounter_id == Encounter.id).options(
        joinedload(Prescription.doctor),
        joinedload(Prescription.items)
    ).filter(
        Prescription.patient_id == current_patient.id,
        Prescription.status != "Cancelled",
        or_(Prescription.encounter_id.is_(None), Encounter.status == "Completed")
    ).order_by(Prescription.date_prescribed.desc()).all()

    for rx in prescriptions:
        doc_name = f"Dr. {rx.doctor.username.capitalize()}" if rx.doctor else "Dr. Attending"
        date_str = rx.date_prescribed.strftime("%b %d, %Y") if rx.date_prescribed else "Recent"

        medications = []
        item_descs = []
        for item in rx.items:
            schedule = []
            for time in ("morning", "afternoon", "evening", "night"):
                dose = (getattr(item, time) or "").strip()
                if dose and dose != "0":
                    schedule.append({"time": time.capitalize(), "dose": dose})
            medications.append({
                "id": item.id,
                "name": (item.molecule or "").strip() or "Medicine name not recorded",
                "schedule": schedule,
                "when": (item.when or "").strip(),
                "durationDays": item.duration_days,
                "instructions": (item.details or "").strip(),
            })
            medication = medications[-1]
            lines = [medication["name"], *(f"{dose['time']}: {dose['dose']}" for dose in schedule)]
            if medication["when"]:
                lines.append(f"When to take: {medication['when']}")
            days = item.duration_days
            duration = f"{days} day{'s' if days != 1 else ''}" if days is not None else "Not recorded"
            lines.append(f"Duration: {duration}")
            if medication["instructions"]:
                lines.append(f"Instructions: {medication['instructions']}")
            item_descs.append("\n".join(lines))

        details_str = "\n\n".join(item_descs) if item_descs else (rx.notes or "No additional prescription notes.")

        history_items.append({
            "id": f"RX-{rx.id}",
            "recordType": "PRESCRIPTION",
            "title": f"Prescription ({len(rx.items)} Medication{'s' if len(rx.items) != 1 else ''})",
            "subtitle": f"Prescribed by {doc_name}",
            "doctorName": doc_name,
            "dateLabel": date_str,
            "details": details_str,
            "badgeLabel": "Prescription",
            "medications": medications,
        })

    # 3. Allergies
    allergies = db.query(Allergy).filter(Allergy.patient_id == current_patient.id).all()
    for alg in allergies:
        history_items.append({
            "id": f"ALG-{alg.id}",
            "recordType": "ALLERGY",
            "title": f"Documented Allergy: {alg.allergen}",
            "subtitle": f"Reaction: {alg.reaction or 'Reported'}",
            "doctorName": "Clinical Care Team",
            "dateLabel": alg.status or "Not recorded",
            "details": f"Patient allergic to {alg.allergen}. Severity: {alg.severity or 'Not recorded'}. Precautions logged in chart.",
            "badgeLabel": "Allergy Alert" if alg.status == "Active" else "Archived Allergy"
        })

    # Return only records documented for this patient.
    immunizations = db.query(Immunization).filter(Immunization.patient_id == current_patient.id).all()
    for item in immunizations:
        history_items.append({
            "id": f"IMM-{item.id}", "recordType": "IMMUNIZATION",
            "title": item.vaccine_name, "subtitle": item.site or "Immunization",
            "doctorName": "Clinical Care Team",
            "dateLabel": item.administered_date.isoformat() if item.administered_date else "Not recorded",
            "details": item.notes or "No additional notes", "badgeLabel": "Immunization"
        })
    return history_items
