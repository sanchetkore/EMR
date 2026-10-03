from sqlalchemy import Column, Integer, String, Date, Text, Float, Boolean, ForeignKey, DateTime, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base


class PatientProblem(Base):
    """Normalized active and chronic problems for Patient Brain."""
    __tablename__ = "patient_problems"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), index=True, nullable=False)
    problem_code = Column(String(64), nullable=True, index=True) # ICD-10 or internal code
    problem_name = Column(String(255), nullable=False, index=True)
    status = Column(String(32), default="active", index=True) # active, resolved, chronic, ruled_out
    diagnosed_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    priority = Column(String(32), default="medium") # high, medium, low
    source_record_id = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    patient = relationship("Patient")
    decisions = relationship("ClinicalDecision", back_populates="problem")
    open_loops = relationship("OpenLoop", back_populates="problem")


class ClinicalEvent(Base):
    """Standardized longitudinal clinical event timeline record."""
    __tablename__ = "clinical_events"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), index=True, nullable=False)
    event_type = Column(String(64), nullable=False, index=True) # lab, medication, vital, diagnosis, decision, referral, loop_created, loop_closed, visit
    event_date = Column(DateTime, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    summary = Column(Text, nullable=True)
    source_type = Column(String(64), nullable=True) # encounter, lab_result, prescription, open_loop, vitals
    source_id = Column(Integer, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    patient = relationship("Patient")


class ClinicalDecision(Base):
    """Longitudinal memory of clinical choices with structured reasons."""
    __tablename__ = "clinical_decisions"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), index=True, nullable=False)
    problem_id = Column(Integer, ForeignKey("patient_problems.id", ondelete="SET NULL"), nullable=True, index=True)
    decision = Column(String(255), nullable=False)
    reason = Column(String(255), nullable=True) # Adverse effect, Ineffective, Target achieved, Patient preference, etc.
    details = Column(Text, nullable=True)
    doctor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    visit_id = Column(Integer, ForeignKey("encounters.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    patient = relationship("Patient")
    problem = relationship("PatientProblem", back_populates="decisions")
    doctor = relationship("User")
    visit = relationship("Encounter")


class OpenLoop(Base):
    """Track pending clinical actions and expectations with auto-closure."""
    __tablename__ = "open_loops"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), index=True, nullable=False)
    problem_id = Column(Integer, ForeignKey("patient_problems.id", ondelete="SET NULL"), nullable=True, index=True)
    type = Column(String(64), nullable=False, index=True) # lab, investigation, referral, follow_up, medication_review
    description = Column(String(255), nullable=False)
    target_code = Column(String(64), nullable=True, index=True) # e.g. HBA1C, CREATININE for auto-matching
    expected_date = Column(Date, nullable=True, index=True)
    status = Column(String(32), default="pending", index=True) # pending, completed, cancelled, overdue
    source_visit_id = Column(Integer, ForeignKey("encounters.id", ondelete="SET NULL"), nullable=True)
    source_order_id = Column(Integer, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    result_id = Column(Integer, nullable=True)
    completion_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    patient = relationship("Patient")
    problem = relationship("PatientProblem", back_populates="open_loops")
    source_visit = relationship("Encounter")


class MedicationEvent(Base):
    """Structured history of medication initiation, titrations, and discontinuations."""
    __tablename__ = "medication_events"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), index=True, nullable=False)
    medication_id = Column(Integer, nullable=True)
    drug_name = Column(String(255), nullable=False, index=True)
    action = Column(String(64), nullable=False, index=True) # started, stopped, dose_increased, dose_decreased, continued, switched
    old_dose = Column(String(128), nullable=True)
    new_dose = Column(String(128), nullable=True)
    reason = Column(String(255), nullable=True) # Adverse effect, Ineffective, Treatment completed, Patient preference, Cost, Other
    reason_details = Column(Text, nullable=True)
    visit_id = Column(Integer, ForeignKey("encounters.id", ondelete="SET NULL"), nullable=True)
    doctor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    patient = relationship("Patient")
    visit = relationship("Encounter")
    doctor = relationship("User")


class PatientFlag(Base):
    """Proactive clinical priority indicators: needs decision, needs attention, FYI."""
    __tablename__ = "patient_flags"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), index=True, nullable=False)
    flag_type = Column(String(64), nullable=False, index=True) # needs_decision, needs_attention, fyi, allergy, critical_metric
    severity = Column(String(32), default="medium") # high, medium, low
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    source_type = Column(String(64), nullable=True)
    source_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    resolved_at = Column(DateTime, nullable=True)

    patient = relationship("Patient")


class BrainSnapshot(Base):
    """Cached versioned snapshots of Patient Brain for performance and audit."""
    __tablename__ = "brain_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), index=True, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    generated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    snapshot_json = Column(JSON, nullable=False)

    patient = relationship("Patient")


class AIInteraction(Base):
    """Audit log for AI token usage, latency, estimated cost, and clinical traceability."""
    __tablename__ = "ai_interactions"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), index=True, nullable=False)
    doctor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(64), nullable=False) # ask_pg, plan_structure, summarize
    model = Column(String(64), nullable=True)
    query = Column(Text, nullable=True)
    response = Column(Text, nullable=True)
    retrieved_sources = Column(JSON, nullable=True)
    input_tokens = Column(Integer, default=0, nullable=False)
    output_tokens = Column(Integer, default=0, nullable=False)
    latency_ms = Column(Integer, default=0, nullable=False)
    estimated_cost = Column(Float, default=0.0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    patient = relationship("Patient")
    doctor = relationship("User")


class BrainCorrection(Base):
    """Doctor override/correction on derived brain facts without mutating raw clinical records."""
    __tablename__ = "brain_corrections"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), index=True, nullable=False)
    doctor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    entity_type = Column(String(64), nullable=False) # problem, trend, medication, open_loop
    entity_id = Column(Integer, nullable=True)
    source_value = Column(Text, nullable=True)
    derived_value = Column(Text, nullable=True)
    doctor_correction = Column(Text, nullable=False)
    corrected_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    patient = relationship("Patient")
    doctor = relationship("User")


class ConversationState(Base):
    """Server-side conversational state for PG assistant to avoid resending full history."""
    __tablename__ = "patient_conversation_states"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), index=True, nullable=False)
    doctor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    active_problem = Column(String(128), nullable=True)
    active_topic = Column(String(128), nullable=True)
    last_intent = Column(String(64), nullable=True)
    last_question = Column(Text, nullable=True)
    last_answer = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    patient = relationship("Patient")
    doctor = relationship("User")
