from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
from datetime import datetime, date


# -------------------------------------------------------------------------
# Patient Problem Schemas
# -------------------------------------------------------------------------
class PatientProblemBase(BaseModel):
    problem_name: str
    problem_code: Optional[str] = None
    status: str = "active" # active, resolved, chronic, ruled_out
    diagnosed_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    priority: str = "medium"
    source_record_id: Optional[str] = None


class PatientProblemCreate(PatientProblemBase):
    pass


class PatientProblemSchema(PatientProblemBase):
    id: int
    patient_id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# -------------------------------------------------------------------------
# Clinical Event Schemas
# -------------------------------------------------------------------------
class ClinicalEventBase(BaseModel):
    event_type: str # lab, medication, vital, diagnosis, decision, referral, loop_created, loop_closed, visit
    event_date: datetime
    title: str
    summary: Optional[str] = None
    source_type: Optional[str] = None
    source_id: Optional[int] = None
    metadata_json: Optional[Dict[str, Any]] = None


class ClinicalEventCreate(ClinicalEventBase):
    patient_id: int


class ClinicalEventSchema(ClinicalEventBase):
    id: int
    patient_id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# -------------------------------------------------------------------------
# Clinical Decision Schemas
# -------------------------------------------------------------------------
class ClinicalDecisionBase(BaseModel):
    decision: str
    reason: Optional[str] = None # Adverse effect, Ineffective, Target achieved, etc.
    details: Optional[str] = None
    problem_id: Optional[int] = None
    visit_id: Optional[int] = None


class ClinicalDecisionCreate(ClinicalDecisionBase):
    doctor_id: Optional[int] = None


class ClinicalDecisionSchema(ClinicalDecisionBase):
    id: int
    patient_id: int
    doctor_id: Optional[int] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# -------------------------------------------------------------------------
# Open Loop Schemas
# -------------------------------------------------------------------------
class OpenLoopBase(BaseModel):
    type: str # lab, investigation, referral, follow_up, medication_review
    description: str
    target_code: Optional[str] = None
    expected_date: Optional[date] = None
    problem_id: Optional[int] = None
    source_visit_id: Optional[int] = None
    source_order_id: Optional[int] = None


class OpenLoopCreate(OpenLoopBase):
    pass


class OpenLoopClose(BaseModel):
    completion_note: Optional[str] = None
    result_id: Optional[int] = None


class OpenLoopSchema(OpenLoopBase):
    id: int
    patient_id: int
    status: str # pending, completed, cancelled, overdue
    is_overdue: bool = False
    days_overdue: int = 0
    completed_at: Optional[datetime] = None
    result_id: Optional[int] = None
    completion_note: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# -------------------------------------------------------------------------
# Medication Event Schemas
# -------------------------------------------------------------------------
class MedicationEventBase(BaseModel):
    drug_name: str
    action: str # started, stopped, dose_increased, dose_decreased, continued, switched
    old_dose: Optional[str] = None
    new_dose: Optional[str] = None
    reason: Optional[str] = None
    reason_details: Optional[str] = None
    medication_id: Optional[int] = None
    visit_id: Optional[int] = None


class MedicationEventCreate(MedicationEventBase):
    doctor_id: Optional[int] = None


class MedicationEventSchema(MedicationEventBase):
    id: int
    patient_id: int
    doctor_id: Optional[int] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# -------------------------------------------------------------------------
# Trend & Metric Schemas (Deterministic)
# -------------------------------------------------------------------------
class TrendPoint(BaseModel):
    date: str
    value: float
    display_value: str
    source_id: Optional[int] = None


class MetricTrend(BaseModel):
    metric_name: str
    code: Optional[str] = None
    category: str # "lab" or "vital"
    unit: Optional[str] = None
    reference_range: Optional[str] = None
    latest_value: Optional[float] = None
    latest_display: str
    latest_date: Optional[str] = None
    previous_value: Optional[float] = None
    previous_display: Optional[str] = None
    previous_date: Optional[str] = None
    delta: Optional[float] = None
    percent_change: Optional[float] = None
    direction: str = "stable" # "increased", "decreased", "stable"
    consecutive_direction_count: int = 0
    clinical_status: str = "normal" # "normal", "abnormal_high", "abnormal_low", "critical"
    history: List[TrendPoint] = []


class PatientTrendsResponse(BaseModel):
    patient_id: int
    lab_trends: List[MetricTrend] = []
    vital_trends: List[MetricTrend] = []


# -------------------------------------------------------------------------
# Since Last Visit Response Schema
# -------------------------------------------------------------------------
class MetricChangeItem(BaseModel):
    test_or_vital: str
    previous: str
    current: str
    delta: Optional[str] = None
    direction: str
    severity: str = "neutral" # "better", "worse", "neutral"


class ChangesSinceLastVisitResponse(BaseModel):
    patient_id: int
    last_visit_date: Optional[str] = None
    days_since_last_visit: Optional[int] = None
    new_results: List[Dict[str, Any]] = []
    medication_changes: List[MedicationEventSchema] = []
    new_diagnoses: List[str] = []
    completed_orders: List[Dict[str, Any]] = []
    pending_orders: List[OpenLoopSchema] = []
    new_documents: List[Dict[str, Any]] = []
    new_referrals: List[Dict[str, Any]] = []
    important_metric_changes: List[MetricChangeItem] = []


# -------------------------------------------------------------------------
# Prepare Patient Response Schema (Section 11)
# -------------------------------------------------------------------------
class PatientDemographicsBrief(BaseModel):
    id: int
    name: str
    age: Optional[int] = None
    gender: Optional[str] = None
    opd_number: Optional[str] = None
    blood_group: Optional[str] = None


class MedicationReasonItem(BaseModel):
    drug_name: str
    action: str
    old_dose: Optional[str] = None
    new_dose: Optional[str] = None
    reason: str
    details: Optional[str] = None
    date: str


class PreparePatientResponse(BaseModel):
    patient: PatientDemographicsBrief
    reason_for_visit: Optional[str] = None
    active_problems: List[PatientProblemSchema] = []
    allergies: List[Dict[str, str]] = []
    since_last_visit_changes: List[MetricChangeItem] = []
    new_completed_reports: List[Dict[str, Any]] = []
    pending_loops: List[OpenLoopSchema] = []
    overdue_loops: List[OpenLoopSchema] = []
    last_plan: Dict[str, Any] = {}
    why_previous_medications_changed: List[MedicationReasonItem] = []
    attention_items: List[Dict[str, Any]] = []


# -------------------------------------------------------------------------
# Patient Brain Full Response Schema (Section 2 & 10)
# -------------------------------------------------------------------------
class PatientBrainProblemView(BaseModel):
    id: int
    name: str
    status: str
    diagnosed_at: Optional[str] = None
    medications: List[str] = []
    latest_metrics: Dict[str, Any] = {}
    trends: Dict[str, List[float]] = {}
    last_plan: Optional[str] = None
    pending: List[str] = []


class PatientBrainResponse(BaseModel):
    patient_id: int
    version: int
    generated_at: str
    active_problems_count: int
    open_loops_count: int
    overdue_loops_count: int
    recent_changes_count: int
    problems: List[PatientBrainProblemView] = []
    needs_attention: List[Dict[str, Any]] = []
    needs_decision: List[Dict[str, Any]] = []
    fyi: List[Dict[str, Any]] = []
    open_loops: List[OpenLoopSchema] = []
    active_medications: List[Dict[str, Any]] = []
    latest_vitals: Dict[str, Any] = {}


# -------------------------------------------------------------------------
# Doctor Brain Correction Schemas (Section 32)
# -------------------------------------------------------------------------
class DoctorCorrectionCreate(BaseModel):
    entity_type: str # problem, trend, medication, open_loop
    entity_id: Optional[int] = None
    source_value: Optional[str] = None
    derived_value: Optional[str] = None
    doctor_correction: str


class DoctorCorrectionResponse(BaseModel):
    id: int
    patient_id: int
    doctor_id: Optional[int] = None
    entity_type: str
    entity_id: Optional[int] = None
    source_value: Optional[str] = None
    derived_value: Optional[str] = None
    doctor_correction: str
    corrected_at: datetime
    model_config = ConfigDict(from_attributes=True)


# -------------------------------------------------------------------------
# PG Assistant Schemas (Section 12-20)
# -------------------------------------------------------------------------
class PGAssistantQuery(BaseModel):
    question: str
    active_problem: Optional[str] = None
    active_topic: Optional[str] = None


class TraceableSource(BaseModel):
    source_type: str # visit, lab, medication_event, open_loop
    source_id: Optional[int] = None
    date: Optional[str] = None
    label: str


class PGAssistantResponse(BaseModel):
    intent: str
    facts: List[str] = []
    pg_observations: List[str] = []
    answer_text: str
    sources: List[TraceableSource] = []
    active_topic: Optional[str] = None
    active_problem: Optional[str] = None
    tokens_used: int = 0
    latency_ms: int = 0
    estimated_cost: float = 0.0


# -------------------------------------------------------------------------
# AI Plan Structuring Schemas (Section 25)
# -------------------------------------------------------------------------
class PlanActionItem(BaseModel):
    type: str # continue_medication, change_medication, stop_medication, investigation, referral, follow_up
    description: str
    drug_name: Optional[str] = None
    dose: Optional[str] = None
    test_name: Optional[str] = None
    due_in: Optional[str] = None
    expected_days: Optional[int] = None


class PlanStructureQuery(BaseModel):
    raw_text: str


class PlanStructureResponse(BaseModel):
    raw_text: str
    actions: List[PlanActionItem] = []
    summary_preview: List[str] = []


class PlanCommitRequest(BaseModel):
    visit_id: Optional[int] = None
    actions: List[PlanActionItem]


# -------------------------------------------------------------------------
# Attention Queue Schemas (Section 8 & 27)
# -------------------------------------------------------------------------
class AttentionItem(BaseModel):
    patient_id: int
    patient_name: str
    opd_number: Optional[str] = None
    category: str # "needs_decision", "needs_attention", "fyi"
    title: str
    detail: str
    source_type: Optional[str] = None
    source_id: Optional[int] = None
    created_at: str


class AttentionQueueResponse(BaseModel):
    needs_decision: List[AttentionItem] = []
    needs_attention: List[AttentionItem] = []
    fyi: List[AttentionItem] = []
    total_count: int = 0
    page: int
    page_size: int
    total_patients: int
    scanned_patients: int
    has_next: bool
    appointment_date: date
