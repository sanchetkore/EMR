"""FastAPI endpoints for Patient Brain and PG Assistant."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from typing import List, Optional, Any

from app.core.database import get_db
from app.core.limiter import limiter
from app.api.deps import RequirePermission, get_current_active_user
from app.models.user import User
from app.schemas.patient_brain import (
    PatientBrainResponse,
    PreparePatientResponse,
    ChangesSinceLastVisitResponse,
    PatientTrendsResponse,
    ClinicalEventSchema,
    OpenLoopSchema,
    OpenLoopCreate,
    OpenLoopClose,
    MedicationEventSchema,
    MedicationEventCreate,
    ClinicalDecisionSchema,
    ClinicalDecisionCreate,
    DoctorCorrectionCreate,
    DoctorCorrectionResponse,
    PGAssistantQuery,
    PGAssistantResponse,
    PlanStructureQuery,
    PlanStructureResponse,
    PlanCommitRequest,
    AttentionQueueResponse,
)
from app.services.patient_brain_service import get_or_build_patient_brain, record_brain_correction
from app.services.prepare_patient_service import get_prepared_patient_brief
from app.services.since_last_visit_service import get_changes_since_last_visit
from app.services.clinical_event_engine import get_patient_timeline, get_problem_timeline
from app.services.trend_engine import calculate_lab_trends, calculate_vital_trends
from app.services.open_loops_engine import get_patient_open_loops, create_open_loop, close_open_loop
from app.services.attention_engine import get_patient_attention_items, get_clinic_attention_queue
from app.services.why_memory_service import record_medication_event, record_clinical_decision, get_medication_intelligence
from app.services.pg_assistant_service import query_pg_assistant
from app.services.plan_structuring_service import parse_plan_text, commit_plan_actions


router = APIRouter()


# -------------------------------------------------------------------------
# Patient Brain & Pre-Visit Preparation Endpoints
# -------------------------------------------------------------------------
@router.get(
    "/patients/{patient_id}/brain",
    response_model=PatientBrainResponse,
    dependencies=[Depends(RequirePermission("view_clinical"))],
)
def get_patient_brain(
    patient_id: int,
    refresh: bool = False,
    db: Session = Depends(get_db),
):
    """Retrieve the persistent structured Patient Brain index for a patient."""
    try:
        return get_or_build_patient_brain(db, patient_id, force_refresh=refresh)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/patients/{patient_id}/prepare",
    response_model=PreparePatientResponse,
    dependencies=[Depends(RequirePermission("view_clinical"))],
)
def prepare_patient(
    patient_id: int,
    db: Session = Depends(get_db),
):
    """Get the 5-10 second Pre-Visit Brief before starting consultation (Section 11)."""
    try:
        return get_prepared_patient_brief(db, patient_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/patients/{patient_id}/changes-since-last-visit",
    response_model=ChangesSinceLastVisitResponse,
    dependencies=[Depends(RequirePermission("view_clinical"))],
)
def changes_since_last_visit(
    patient_id: int,
    db: Session = Depends(get_db),
):
    """Get all clinical changes, reports, and medication differences since last visit (Section 22)."""
    return get_changes_since_last_visit(db, patient_id)


# -------------------------------------------------------------------------
# Longitudinal Timelines & Trends
# -------------------------------------------------------------------------
@router.get(
    "/patients/{patient_id}/timeline",
    response_model=List[ClinicalEventSchema],
    dependencies=[Depends(RequirePermission("view_clinical"))],
)
def get_timeline(
    patient_id: int,
    limit: int = 100,
    event_type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Get standardized longitudinal clinical events timeline (Section 4)."""
    return get_patient_timeline(db, patient_id, limit=limit, event_type=event_type)


@router.get(
    "/patients/{patient_id}/problems/{problem_name}/timeline",
    response_model=List[ClinicalEventSchema],
    dependencies=[Depends(RequirePermission("view_clinical"))],
)
def get_problem_specific_timeline(
    patient_id: int,
    problem_name: str,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """Get problem-specific longitudinal timeline (Section 21)."""
    return get_problem_timeline(db, patient_id, problem_name, limit=limit)


@router.get(
    "/patients/{patient_id}/trends",
    response_model=PatientTrendsResponse,
    dependencies=[Depends(RequirePermission("view_clinical"))],
)
def get_patient_trends(
    patient_id: int,
    db: Session = Depends(get_db),
):
    """Get deterministic lab and vital trends with deltas and directions (Section 9)."""
    lab_trends = calculate_lab_trends(db, patient_id)
    vital_trends = calculate_vital_trends(db, patient_id)
    return PatientTrendsResponse(
        patient_id=patient_id,
        lab_trends=lab_trends,
        vital_trends=vital_trends,
    )


# -------------------------------------------------------------------------
# Open Loops Endpoints (Section 6 & 7)
# -------------------------------------------------------------------------
@router.get(
    "/patients/{patient_id}/open-loops",
    response_model=List[OpenLoopSchema],
    dependencies=[Depends(RequirePermission("view_clinical"))],
)
def list_open_loops(
    patient_id: int,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Get pending, completed, or overdue open loops for a patient."""
    return get_patient_open_loops(db, patient_id, status_filter=status)


@router.post(
    "/patients/{patient_id}/open-loops",
    response_model=OpenLoopSchema,
    dependencies=[Depends(RequirePermission("manage_clinical"))],
)
def add_open_loop(
    patient_id: int,
    payload: OpenLoopCreate,
    db: Session = Depends(get_db),
):
    """Create a new open loop for a patient."""
    loop = create_open_loop(
        db=db,
        patient_id=patient_id,
        loop_type=payload.type,
        description=payload.description,
        expected_date=payload.expected_date,
        target_code=payload.target_code,
        problem_id=payload.problem_id,
        source_visit_id=payload.source_visit_id,
        source_order_id=payload.source_order_id,
    )
    loops = get_patient_open_loops(db, patient_id)
    for l in loops:
        if l.id == loop.id:
            return l
    raise HTTPException(status_code=500, detail="Loop could not be retrieved")


@router.post(
    "/patients/{patient_id}/open-loops/{loop_id}/close",
    response_model=OpenLoopSchema,
    dependencies=[Depends(RequirePermission("manage_clinical"))],
)
def complete_open_loop(
    patient_id: int,
    loop_id: int,
    payload: OpenLoopClose,
    db: Session = Depends(get_db),
):
    """Complete an open loop manually."""
    loop = close_open_loop(db, loop_id, completion_note=payload.completion_note, result_id=payload.result_id)
    if not loop:
        raise HTTPException(status_code=404, detail="Open Loop not found")
    loops = get_patient_open_loops(db, patient_id)
    for l in loops:
        if l.id == loop.id:
            return l
    raise HTTPException(status_code=500, detail="Loop could not be retrieved")


# -------------------------------------------------------------------------
# 'Why?' Clinical Memory & Prescription Intelligence (Section 5 & 23)
# -------------------------------------------------------------------------
@router.get(
    "/patients/{patient_id}/medication-intelligence",
    dependencies=[Depends(RequirePermission("view_clinical"))],
)
def get_med_intelligence(
    patient_id: int,
    drug: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Get patient-specific longitudinal medication history and reasons."""
    return get_medication_intelligence(db, patient_id, drug_name=drug)


@router.post(
    "/patients/{patient_id}/medication-events",
    response_model=MedicationEventSchema,
    dependencies=[Depends(RequirePermission("manage_clinical"))],
)
def add_medication_event(
    patient_id: int,
    payload: MedicationEventCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Record a medication start/stop/titration event with reason."""
    event = record_medication_event(
        db=db,
        patient_id=patient_id,
        drug_name=payload.drug_name,
        action=payload.action,
        old_dose=payload.old_dose,
        new_dose=payload.new_dose,
        reason=payload.reason,
        reason_details=payload.reason_details,
        medication_id=payload.medication_id,
        visit_id=payload.visit_id,
        doctor_id=current_user.id,
    )
    return event


@router.post(
    "/patients/{patient_id}/clinical-decisions",
    response_model=ClinicalDecisionSchema,
    dependencies=[Depends(RequirePermission("manage_clinical"))],
)
def add_clinical_decision(
    patient_id: int,
    payload: ClinicalDecisionCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Record a clinical decision with reason."""
    dec = record_clinical_decision(
        db=db,
        patient_id=patient_id,
        decision=payload.decision,
        reason=payload.reason,
        details=payload.details,
        problem_id=payload.problem_id,
        doctor_id=current_user.id,
        visit_id=payload.visit_id,
    )
    return dec


# -------------------------------------------------------------------------
# Doctor Corrections (Section 32)
# -------------------------------------------------------------------------
@router.post(
    "/patients/{patient_id}/brain/correct",
    response_model=DoctorCorrectionResponse,
    dependencies=[Depends(RequirePermission("manage_clinical"))],
)
def doctor_brain_correction(
    patient_id: int,
    payload: DoctorCorrectionCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Record doctor override on derived brain state without modifying raw records."""
    correction = record_brain_correction(
        db=db,
        patient_id=patient_id,
        doctor_id=current_user.id,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        source_value=payload.source_value,
        derived_value=payload.derived_value,
        doctor_correction=payload.doctor_correction,
    )
    return correction


# -------------------------------------------------------------------------
# PG Assistant (Section 12-20)
# -------------------------------------------------------------------------
@router.post(
    "/patients/{patient_id}/pg-assistant/ask",
    response_model=PGAssistantResponse,
    dependencies=[Depends(RequirePermission("view_clinical"))],
)
@limiter.limit("30/minute")
def ask_pg_assistant(
    request: Request,
    patient_id: int,
    query: PGAssistantQuery,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Query PG Assistant with minimal tokens, server-side context, and source traceability."""
    return query_pg_assistant(
        db=db,
        patient_id=patient_id,
        doctor_id=current_user.id,
        question=query.question,
        active_problem_override=query.active_problem,
        active_topic_override=query.active_topic,
    )


# -------------------------------------------------------------------------
# AI Plan Structuring (Section 25)
# -------------------------------------------------------------------------
@router.post(
    "/patients/{patient_id}/plan/structure",
    response_model=PlanStructureResponse,
    dependencies=[Depends(RequirePermission("manage_clinical"))],
)
@limiter.limit("20/minute")
def structure_plan_text(
    request: Request,
    patient_id: int,
    payload: PlanStructureQuery,
):
    """Parse short doctor instructions into proposed structured plan items."""
    return parse_plan_text(payload.raw_text)


@router.post(
    "/patients/{patient_id}/plan/commit",
    dependencies=[Depends(RequirePermission("manage_clinical"))],
)
def commit_plan(
    patient_id: int,
    payload: PlanCommitRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Persist confirmed structured plan actions into ClinicalDecisions and OpenLoops."""
    return commit_plan_actions(
        db=db,
        patient_id=patient_id,
        visit_id=payload.visit_id,
        doctor_id=current_user.id,
        actions=payload.actions,
    )


# -------------------------------------------------------------------------
# Doctor Morning Dashboard & Attention Queue (Section 8 & 27)
# -------------------------------------------------------------------------
@router.get(
    "/dashboard/attention-queue",
    response_model=AttentionQueueResponse,
    dependencies=[Depends(RequirePermission("view_clinical"))],
)
def get_attention_queue(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
):
    """Paginated priority queue for patients with appointments today."""
    return get_clinic_attention_queue(db, page=page, page_size=page_size)


@router.get(
    "/patients/{patient_id}/attention",
    dependencies=[Depends(RequirePermission("view_clinical"))],
)
def get_single_patient_attention(
    patient_id: int,
    db: Session = Depends(get_db),
):
    """Actionable attention items for a specific patient."""
    return get_patient_attention_items(db, patient_id)
