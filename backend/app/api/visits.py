from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime, timedelta, date
from app.core.database import get_db
from app.models.encounter import Encounter, EncounterAmendment, PatientVital, VisitComplaint, VisitDiagnosis, VisitTreatment, VitalConfiguration
from app.models.visit_lab_intent import VisitLabOrderIntent
from app.models.lab_result import LabResult, LabCatalog
from app.models.prescription import Prescription, PrescriptionItem
from app.models.patient import Appointment
from app.core.websocket import manager
from app.api.queue import get_live_queue
from app.schemas.encounter import VisitPayload, VisitResponse, VitalConfiguration as VitalConfigurationSchema, VitalConfigurationBase, VisitUpdate, FollowupResponse, AmendmentCreate, Amendment as AmendmentSchema, VisitLabOrderIntent as VisitLabOrderIntentSchema
from app.schemas.encounter import Encounter as EncounterSchema, PatientVital as PatientVitalSchema, VisitComplaint as VisitComplaintSchema, VisitDiagnosis as VisitDiagnosisSchema, VisitTreatment as VisitTreatmentSchema
from app.schemas.prescription import Prescription as PrescriptionSchema
from app.schemas.patient import Appointment as AppointmentSchema
from app.api.deps import RequirePermission
from app.models.user import User
from app.services.lis_order_intents import process_lab_intent
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


def _saved_lis_connection_id(db: Session) -> str:
    from app.api.lis_integration import _load_config

    config = _load_config(db)
    connection_id = config.get("connection_id") if config else None
    if not connection_id:
        raise HTTPException(status_code=409, detail="Reconnect the LIS before requesting tests from a visit")
    return connection_id

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
    # Find the most recent completed encounter for this patient
    encounter = db.query(Encounter).filter(
        Encounter.patient_id == patient_id,
        Encounter.status == "Completed"
    ).order_by(Encounter.encounter_date.desc()).first()

    if not encounter:
        raise HTTPException(status_code=404, detail="No previous visits found for this patient")

    return _build_visit_response(encounter)

@router.get("/history/{patient_id}", response_model=List[VisitResponse], dependencies=[Depends(RequirePermission("view_clinical"))])
def get_visit_history(patient_id: int, limit: int = 6, db: Session = Depends(get_db)):
    # Find the most recent encounters for this patient, up to the limit (default 6)
    encounters = db.query(Encounter).options(
        selectinload(Encounter.vitals),
        selectinload(Encounter.complaints),
        selectinload(Encounter.diagnoses),
        selectinload(Encounter.treatments),
        selectinload(Encounter.prescriptions).selectinload(Prescription.items),
        joinedload(Encounter.appointment),
        selectinload(Encounter.lab_results),
        selectinload(Encounter.amendments),
        joinedload(Encounter.lab_order_intent),
    ).filter(Encounter.patient_id == patient_id).order_by(Encounter.encounter_date.desc()).limit(limit).all()

    return [_build_visit_response(enc) for enc in encounters]

@router.get("/suggestions/diagnoses", dependencies=[Depends(RequirePermission("view_clinical"))])
def get_diagnosis_suggestions(q: str = "", db: Session = Depends(get_db)):
    """Return distinct diagnoses from past visits, ordered by frequency."""
    if not q or len(q) < 2:
        # Return top 15 most common diagnoses
        results = db.query(
            func.max(VisitDiagnosis.diagnosis),
            func.count(VisitDiagnosis.diagnosis).label('count')
        ).group_by(func.lower(VisitDiagnosis.diagnosis)).order_by(
            func.count(VisitDiagnosis.diagnosis).desc()
        ).limit(15).all()
    else:
        results = db.query(
            func.max(VisitDiagnosis.diagnosis),
            func.count(VisitDiagnosis.diagnosis).label('count')
        ).filter(
            func.lower(VisitDiagnosis.diagnosis).like(f"%{q.lower()}%")
        ).group_by(func.lower(VisitDiagnosis.diagnosis)).order_by(
            func.count(VisitDiagnosis.diagnosis).desc()
        ).limit(15).all()

    return [{"text": r[0], "count": r[1]} for r in results]

@router.get("/suggestions/treatments", dependencies=[Depends(RequirePermission("view_clinical"))])
def get_treatment_suggestions(q: str = "", db: Session = Depends(get_db)):
    """Return distinct treatments from past visits, ordered by frequency."""
    if not q or len(q) < 2:
        results = db.query(
            func.max(VisitTreatment.treatment),
            func.count(VisitTreatment.treatment).label('count')
        ).group_by(func.lower(VisitTreatment.treatment)).order_by(
            func.count(VisitTreatment.treatment).desc()
        ).limit(15).all()
    else:
        results = db.query(
            func.max(VisitTreatment.treatment),
            func.count(VisitTreatment.treatment).label('count')
        ).filter(
            func.lower(VisitTreatment.treatment).like(f"%{q.lower()}%")
        ).group_by(func.lower(VisitTreatment.treatment)).order_by(
            func.count(VisitTreatment.treatment).desc()
        ).limit(15).all()

    return [{"text": r[0], "count": r[1]} for r in results]

@router.get("/{encounter_id}", response_model=VisitResponse, dependencies=[Depends(RequirePermission("view_clinical"))])
def get_visit_by_id(encounter_id: int, db: Session = Depends(get_db)):
    encounter = db.query(Encounter).filter(Encounter.id == encounter_id).first()
    if not encounter:
        raise HTTPException(status_code=404, detail="Visit not found")

    return _build_visit_response(encounter)

@router.post("/", response_model=VisitResponse)
def create_visit(payload: VisitPayload, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(RequirePermission("manage_clinical"))):
    if payload.status == "Completed" and current_user.id != payload.doctor_id:
        raise HTTPException(status_code=403, detail="Only the assigned clinician can complete this visit")
    if payload.appointment_id:
        appointment = db.query(Appointment).filter(Appointment.id == payload.appointment_id).first()
        if not appointment or appointment.patient_id != payload.patient_id:
            raise HTTPException(status_code=422, detail="Appointment does not belong to this patient")
    # 1. Create Encounter
    # Auto-calculate visit number
    max_visit = db.query(func.max(Encounter.visit_number)).filter(Encounter.patient_id == payload.patient_id).scalar() or 0
    visit_num = max_visit + 1

    db_encounter = Encounter(
        patient_id=payload.patient_id,
        doctor_id=payload.doctor_id,
        appointment_id=payload.appointment_id,
        reason=payload.reason,
        notes=payload.notes,
        draft_orders=payload.draft_orders,
        quick_notes=payload.quick_notes,
        advice=payload.advice,
        visit_number=visit_num,
        status=payload.status,
        signed_at=datetime.utcnow() if payload.status == "Completed" else None,
        signed_by_id=current_user.id if payload.status == "Completed" else None,
        followup_days=payload.followup_days,
        followup_date=payload.followup_date if payload.followup_date else (
            (datetime.utcnow() + timedelta(days=payload.followup_days)).date() if payload.followup_days else (
                (datetime.utcnow() + timedelta(days=payload.followup_months * 30)).date() if payload.followup_months else None
            )
        )
    )
    db.add(db_encounter)
    db.flush() # flush to get the encounter id without committing the transaction yet
    if payload.lis_order:
        db.add(VisitLabOrderIntent(
            encounter_id=db_encounter.id,
            patient_id=payload.patient_id,
            requested_by_id=current_user.id,
            source_id=f"visit-{db_encounter.id}",
            connection_id=_saved_lis_connection_id(db),
            test_codes=list(dict.fromkeys(payload.lis_order.test_codes)),
            package_codes=list(dict.fromkeys(payload.lis_order.package_codes)),
            notes=payload.lis_order.notes,
            status="PENDING",
        ))

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
    if payload.lab_test_catalogs:
        catalogs = db.query(LabCatalog).filter(LabCatalog.id.in_(payload.lab_test_catalogs)).all()
        for catalog_item in catalogs:
            db_lab = LabResult(
                patient_id=payload.patient_id,
                encounter_id=db_encounter.id,
                catalog_id=catalog_item.id,
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
            encounter_id=db_encounter.id,
            notes=f"Created during Visit #{visit_num}"
        )
        db.add(db_prescription)
        db.flush()

        for p_item in payload.prescriptions:
            p_dict = p_item.dict()
            if not p_dict.get("molecule") and p_dict.get("name"):
                p_dict["molecule"] = p_dict["name"]

            db_p_item = PrescriptionItem(
                prescription_id=db_prescription.id,
                **{k: v for k, v in p_dict.items() if k != "name"}
            )
            db.add(db_p_item)

        from app.services.whatsapp_service import send_prescription_whatsapp
        from app.services.sms_service import send_prescription_sms
        if payload.status == "Completed":
            background_tasks.add_task(send_prescription_whatsapp, db_prescription.patient_id, db_prescription.doctor_id, db_prescription.id)
            background_tasks.add_task(send_prescription_sms, db_prescription.patient_id, db_prescription.doctor_id)

    if payload.appointment_id and payload.status:
        appointment.status = payload.status

    # Commit the encounter and appointment together.
    db.commit()
    db.refresh(db_encounter)

    # Sync status to appointment
    if payload.status == "Completed":
        try:
            from app.services.ai_summary_service import background_ai_summary_task
        except ImportError:
            logger.warning("AI summary service unavailable; the completed visit remains saved")
            background_ai_summary_task = None
        import json

        new_data_dict = {
            "visit_number": db_encounter.visit_number,
            "complaints": [c.complaint for c in payload.complaints],
            "diagnoses": [d.diagnosis for d in payload.diagnoses],
            "treatments": [t.treatment for t in payload.treatments],
            "notes": payload.notes
        }
        if background_ai_summary_task:
            background_tasks.add_task(
                background_ai_summary_task,
                patient_id=db_encounter.patient_id,
                new_data_str=f"Visit Date: {datetime.utcnow().date()}\n" + json.dumps(new_data_dict, indent=2)
            )

    if payload.appointment_id and payload.status:
        try:
            queue_payload = get_live_queue(db)
            background_tasks.add_task(manager.broadcast, queue_payload)
        except Exception:
            logger.exception("Queue update failed after visit creation")

    return _build_visit_response(db_encounter, db)

@router.put("/{encounter_id}", response_model=VisitResponse)
def update_visit(encounter_id: int, payload: VisitUpdate, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(RequirePermission("manage_clinical"))):
    db_encounter = db.query(Encounter).filter(Encounter.id == encounter_id).first()
    if not db_encounter:
        raise HTTPException(status_code=404, detail="Visit not found")
    if db_encounter.status == "Completed":
        raise HTTPException(status_code=409, detail="Completed visits are protected. Add an amendment instead.")
    if payload.status == "Completed" and current_user.id != db_encounter.doctor_id:
        raise HTTPException(status_code=403, detail="Only the assigned clinician can complete this visit")
    if payload.patient_id is not None and payload.patient_id != db_encounter.patient_id:
        raise HTTPException(status_code=422, detail="Cannot change the visit patient")
    if payload.doctor_id is not None and payload.doctor_id != db_encounter.doctor_id:
        raise HTTPException(status_code=422, detail="Cannot change the visit doctor")
    if payload.appointment_id is not None and payload.appointment_id != db_encounter.appointment_id:
        raise HTTPException(status_code=422, detail="Cannot change the visit appointment")

    # Claim the exact revision before any writes. A concurrent editor cannot
    # silently overwrite a saved consultation or complete it twice.
    updated = db.query(Encounter).filter(
        Encounter.id == encounter_id,
        Encounter.version == payload.expected_version,
        Encounter.status != "Completed",
    ).update({Encounter.version: Encounter.version + 1}, synchronize_session=False)
    if updated != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="This visit changed in another session. Reload before saving.")
    db.refresh(db_encounter)

    update_data = payload.model_dump(exclude_unset=True)
    prescriptions_data = update_data.pop("prescriptions", None)
    lab_test_catalogs_data = update_data.pop("lab_test_catalogs", None)
    lis_order_data = update_data.pop("lis_order", None)
    if lis_order_data:
        existing_intent = db.query(VisitLabOrderIntent).filter(VisitLabOrderIntent.encounter_id == encounter_id).first()
        requested_tests = list(dict.fromkeys(lis_order_data["test_codes"]))
        requested_packages = list(dict.fromkeys(lis_order_data.get("package_codes") or []))
        if existing_intent:
            if sorted(existing_intent.test_codes) != sorted(requested_tests) or sorted(existing_intent.package_codes) != sorted(requested_packages):
                db.rollback()
                raise HTTPException(status_code=409, detail="This visit already has a laboratory request with different tests. Create an explicit new order.")
        else:
            db.add(VisitLabOrderIntent(
                encounter_id=encounter_id,
                patient_id=db_encounter.patient_id,
                requested_by_id=current_user.id,
                source_id=f"visit-{encounter_id}",
                connection_id=_saved_lis_connection_id(db),
                test_codes=requested_tests,
                package_codes=requested_packages,
                notes=lis_order_data.get("notes"),
                status="PENDING",
            ))
    collection_data = {
        "vitals": update_data.pop("vitals", None),
        "complaints": update_data.pop("complaints", None),
        "diagnoses": update_data.pop("diagnoses", None),
        "treatments": update_data.pop("treatments", None),
    }
    for identity_field in ("patient_id", "doctor_id", "appointment_id"):
        update_data.pop(identity_field, None)
    update_data.pop("expected_version", None)
    if update_data.get("status") == "Completed":
        db_encounter.signed_at = datetime.utcnow()
        db_encounter.signed_by_id = current_user.id
    # Handle followup date auto-calculation if days or months are provided but date is not
    if "followup_date" not in update_data:
        if update_data.get("followup_days") is not None:
            update_data["followup_date"] = (datetime.utcnow() + timedelta(days=update_data["followup_days"])).date()
        elif update_data.get("followup_months") is not None:
            update_data["followup_date"] = (datetime.utcnow() + timedelta(days=update_data["followup_months"] * 30)).date()
        elif "followup_days" in update_data or "followup_months" in update_data:
            update_data["followup_date"] = None

    # We no longer save followup_months in the DB, so remove it from update_data to prevent setattr errors
    update_data.pop("followup_months", None)

    for key, value in update_data.items():
        setattr(db_encounter, key, value)

    for key, model in (
        ("vitals", PatientVital),
        ("complaints", VisitComplaint),
        ("diagnoses", VisitDiagnosis),
        ("treatments", VisitTreatment),
    ):
        items = collection_data[key]
        if items is None:
            continue
        db.query(model).filter(model.encounter_id == encounter_id).delete(synchronize_session=False)
        for item in items:
            db.add(model(encounter_id=encounter_id, **item))

    # Handle prescriptions update
    if prescriptions_data is not None:
        db_prescription = db.query(Prescription).filter(Prescription.encounter_id == encounter_id).first()
        if not db_prescription:
            db_prescription = Prescription(
                patient_id=db_encounter.patient_id,
                doctor_id=db_encounter.doctor_id,
                encounter_id=encounter_id,
                notes=f"Updated during Visit #{db_encounter.visit_number}"
            )
            db.add(db_prescription)
            db.flush()
        else:
            db.query(PrescriptionItem).filter(PrescriptionItem.prescription_id == db_prescription.id).delete()
            db.flush()

        for p_item in prescriptions_data:
            valid_keys = {"molecule", "morning", "afternoon", "evening", "night", "when", "details"}
            filtered_item = {k: v for k, v in p_item.items() if k in valid_keys}

            # Ensure required field 'molecule' exists (fallback to empty string if frontend sends something else)
            if "molecule" not in filtered_item or not filtered_item["molecule"]:
                filtered_item["molecule"] = p_item.get("name", p_item.get("drug_name", "")) # Best effort fallback

            db_p_item = PrescriptionItem(
                prescription_id=db_prescription.id,
                **filtered_item
            )
            db.add(db_p_item)
        from app.services.whatsapp_service import send_prescription_whatsapp
        from app.services.sms_service import send_prescription_sms
        if db_encounter.status == "Completed":
            background_tasks.add_task(send_prescription_whatsapp, db_encounter.patient_id, db_encounter.doctor_id, db_prescription.id)
            background_tasks.add_task(send_prescription_sms, db_encounter.patient_id, db_encounter.doctor_id)

    # Handle lab orders update
    if lab_test_catalogs_data is not None:
        # Delete existing pending lab orders for this encounter
        db.query(LabResult).filter(LabResult.encounter_id == encounter_id, LabResult.status == "Pending").delete()
        db.flush()

        # Add new lab orders
        if lab_test_catalogs_data:
            catalogs = db.query(LabCatalog).filter(LabCatalog.id.in_(lab_test_catalogs_data)).all()
            for catalog_item in catalogs:
                db_lab = LabResult(
                    patient_id=db_encounter.patient_id,
                    encounter_id=db_encounter.id,
                    catalog_id=catalog_item.id,
                    test_name=catalog_item.name,
                    status="Pending",
                    ordered_by=db_encounter.doctor_id
                )
                db.add(db_lab)
    if db_encounter.appointment_id and db_encounter.status in ("Completed", "Cancelled", "No Show"):
        db_appointment = db.query(Appointment).filter(Appointment.id == db_encounter.appointment_id).first()
        if db_appointment:
            db_appointment.status = db_encounter.status

    db.commit()
    db.refresh(db_encounter)

    # Sync status to appointment
    if "status" in update_data and update_data["status"] == "Completed":
        # Format the new visit data
        try:
            from app.services.ai_summary_service import background_ai_summary_task
        except ImportError:
            logger.warning("AI summary service unavailable; the completed visit remains saved")
            background_ai_summary_task = None
        import json

        # Prepare a simple text representation of the new visit data
        new_data_dict = {
            "visit_number": db_encounter.visit_number,
            "complaints": [c.complaint for c in db.query(VisitComplaint).filter(VisitComplaint.encounter_id == encounter_id).all()],
            "diagnoses": [d.diagnosis for d in db.query(VisitDiagnosis).filter(VisitDiagnosis.encounter_id == encounter_id).all()],
            "treatments": [t.treatment for t in db.query(VisitTreatment).filter(VisitTreatment.encounter_id == encounter_id).all()],
            "notes": db_encounter.notes
        }

        if background_ai_summary_task:
            background_tasks.add_task(
                background_ai_summary_task,
                patient_id=db_encounter.patient_id,
                new_data_str=f"Visit Date: {datetime.utcnow().date()}\n" + json.dumps(new_data_dict, indent=2)
            )
        try:
            from app.services.open_loops_engine import match_open_loops
            match_open_loops(db, patient_id=db_encounter.patient_id, event_type="visit", test_name_or_code="Follow-up")
            from app.services.patient_brain_service import get_or_build_patient_brain
            get_or_build_patient_brain(db, db_encounter.patient_id, force_refresh=True)
        except Exception:
            pass

    if db_encounter.status == "Completed" and db_encounter.appointment_id:
        try:
            queue_payload = get_live_queue(db)
            background_tasks.add_task(manager.broadcast, queue_payload)
        except Exception:
            logger.exception("Queue update failed after visit completion")

    return _build_visit_response(db_encounter, db)


@router.post("/{encounter_id}/amendments", response_model=AmendmentSchema)
def add_visit_amendment(encounter_id: int, payload: AmendmentCreate, db: Session = Depends(get_db), current_user: User = Depends(RequirePermission("manage_clinical"))):
    encounter = db.query(Encounter).filter(Encounter.id == encounter_id).first()
    if not encounter:
        raise HTTPException(status_code=404, detail="Visit not found")
    if encounter.status != "Completed":
        raise HTTPException(status_code=409, detail="Save changes to the open visit before creating an amendment")
    amendment = EncounterAmendment(
        encounter_id=encounter_id,
        author_id=current_user.id,
        reason=payload.reason.strip(),
        note=payload.note.strip(),
    )
    if not amendment.reason or not amendment.note:
        raise HTTPException(status_code=422, detail="Reason and note are required")
    db.add(amendment)
    db.commit()
    db.refresh(amendment)
    return amendment


@router.get("/{encounter_id}/lab-order", response_model=VisitLabOrderIntentSchema, dependencies=[Depends(RequirePermission("view_clinical"))])
def get_visit_lab_order(encounter_id: int, db: Session = Depends(get_db)):
    intent = db.query(VisitLabOrderIntent).filter(VisitLabOrderIntent.encounter_id == encounter_id).first()
    if not intent:
        raise HTTPException(status_code=404, detail="No laboratory request is recorded for this visit")
    return intent


@router.post("/{encounter_id}/lab-order/submit", response_model=VisitLabOrderIntentSchema, dependencies=[Depends(RequirePermission("manage_clinical"))])
def submit_visit_lab_order(encounter_id: int, db: Session = Depends(get_db)):
    intent = db.query(VisitLabOrderIntent).filter(VisitLabOrderIntent.encounter_id == encounter_id).first()
    if not intent:
        raise HTTPException(status_code=404, detail="No laboratory request is recorded for this visit")
    return process_lab_intent(db, intent.id, force=True)

@router.get("/followups/upcoming", response_model=List[FollowupResponse], dependencies=[Depends(RequirePermission("view_clinical"))])
def get_upcoming_followups(
    days: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    doctor_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Encounter).filter(Encounter.followup_date != None, Encounter.status == "Completed")

    if start_date:
        query = query.filter(Encounter.followup_date >= start_date)
    else:
        # Default to today onwards
        start_date = datetime.utcnow().date()
        query = query.filter(Encounter.followup_date >= start_date)

    if days is not None:
        end_date = start_date + timedelta(days=days)

    if end_date:
        query = query.filter(Encounter.followup_date <= end_date)

    if doctor_id:
        query = query.filter(Encounter.doctor_id == doctor_id)

    query = query.options(joinedload(Encounter.patient), joinedload(Encounter.doctor)).order_by(Encounter.followup_date.asc())
    encounters = query.all()

    results = []
    for enc in encounters:
        patient_name = f"{enc.patient.first_name} {enc.patient.last_name}" if enc.patient else "Unknown"
        patient_phone = enc.patient.contact_number if enc.patient else None
        doctor_name = enc.doctor.username if enc.doctor else "Unknown"

        results.append(FollowupResponse(
            encounter_id=enc.id,
            patient_id=enc.patient_id,
            patient_name=patient_name,
            patient_phone=patient_phone,
            doctor_name=doctor_name,
            last_visit_date=enc.encounter_date,
            followup_date=enc.followup_date,
            followup_days=enc.followup_days,
            reason=enc.reason,
            visit_number=enc.visit_number
        ))

    return results

def _build_visit_response(encounter, db=None):
    """Convert ORM encounter and its relations into a VisitResponse dict."""
    prescriptions = []
    for p in encounter.prescriptions:
        p_schema = PrescriptionSchema.model_validate(p, from_attributes=True)
        for item in p_schema.items:
            item.name = item.molecule
        prescriptions.append(p_schema)

    appointment_data = None
    if encounter.appointment:
        appointment_data = AppointmentSchema.model_validate(encounter.appointment, from_attributes=True)

    lab_results_data = []
    from app.schemas.lab_result import LabResult as LabResultSchema
    if hasattr(encounter, 'lab_results'):
        lab_results_data = [LabResultSchema.model_validate(l, from_attributes=True).model_dump() for l in encounter.lab_results]
    elif db:
        from app.models.lab_result import LabResult
        labs = db.query(LabResult).filter(LabResult.encounter_id == encounter.id).all()
        lab_results_data = [LabResultSchema.model_validate(l, from_attributes=True).model_dump() for l in labs]

    return VisitResponse(
        encounter=EncounterSchema.model_validate(encounter, from_attributes=True),
        amendments=[AmendmentSchema.model_validate(a, from_attributes=True) for a in encounter.amendments],
        lab_order_intent=VisitLabOrderIntentSchema.model_validate(encounter.lab_order_intent, from_attributes=True) if encounter.lab_order_intent else None,
        vitals=[PatientVitalSchema.model_validate(v, from_attributes=True) for v in encounter.vitals],
        complaints=[VisitComplaintSchema.model_validate(c, from_attributes=True) for c in encounter.complaints],
        diagnoses=[VisitDiagnosisSchema.model_validate(d, from_attributes=True) for d in encounter.diagnoses],
        treatments=[VisitTreatmentSchema.model_validate(t, from_attributes=True) for t in encounter.treatments],
        prescriptions=prescriptions,
        lab_results=lab_results_data,
        appointment=appointment_data,
    )
