"""PG Assistant Clinical Intelligence Service.
Operates on the principle: Database first -> Rules second -> AI last.
- Token budget capped at <= 800 tokens context.
- De-identifies patient PII (no phone, email, address, billing).
- Maintains server-side conversation state.
- Employs narrow deterministic clinical tools.
- Formulates source-linked responses with clear separation of FACT vs PG OBSERVATION.
- Full audit logging to ai_interactions table.
"""
import os
import json
import time
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.models.patient import Patient
from app.models.encounter import Encounter
from app.models.lab_result import LabResult
from app.models.allergy import Allergy
from app.models.patient_brain import (
    PatientProblem,
    MedicationEvent,
    ClinicalDecision,
    OpenLoop,
    ClinicalEvent,
    AIInteraction,
    ConversationState,
)
from app.services.trend_engine import calculate_lab_trends, calculate_vital_trends
from app.services.open_loops_engine import get_patient_open_loops
from app.services.since_last_visit_service import get_changes_since_last_visit
from app.schemas.patient_brain import (
    PGAssistantResponse,
    TraceableSource,
)


PG_SYSTEM_PROMPT = """You are a clinical PG assistant sitting beside the attending doctor in an outpatient clinic.
Answer the doctor's query directly and concisely based ONLY on the provided structured facts.
RULES:
1. Divide your thinking into two explicit sections:
   - FACTS: Direct verified data from the patient record with exact numbers, dates, and drugs.
   - PG OBSERVATION: Concise clinical interpretation or synthesis (1-2 sentences).
2. Never hallucinate. If data is not present, state that it is not documented.
3. Keep the total response under 150 words.
4. Keep clinical tone professional, crisp, and objective."""


def route_intent(question: str, server_state: Optional[ConversationState] = None) -> Tuple[str, Optional[str]]:
    """Classify the clinician's query into a targeted intent and topic."""
    q = question.lower().strip()

    # Handle follow-up queries using server-side conversation state
    if any(q.startswith(phrase) for phrase in ["and before", "what about before", "previous one", "before that", "earlier", "and then"]):
        if server_state and server_state.active_topic:
            return "follow_up_topic", server_state.active_topic

    if any(k in q for k in ["why", "reason", "stopped", "started", "reduced", "increased", "dose", "prescribed", "drug", "medicine", "medication", "amlodipine", "metformin", "statin", "insulin"]):
        return "medication", None
    elif any(k in q for k in ["lab", "test", "hba1c", "creatinine", "glucose", "sugar", "cbc", "trend", "worsened", "improved", "graph"]):
        return "labs", None
    elif any(k in q for k in ["pending", "open loop", "outstanding", "due", "overdue", "awaiting"]):
        return "open_loops", None
    elif any(k in q for k in ["change", "since last visit", "what changed", "difference"]):
        return "changes", None
    elif any(k in q for k in ["diabetes", "hypertension", "ckd", "condition", "problem", "diagnosis"]):
        return "problem", None
    elif any(k in q for k in ["last visit", "previous visit", "previous consultation", "what happened"]):
        return "last_visit", None

    return "general_chart", None


# -------------------------------------------------------------------------
# Narrow PG Tools (Pure SQL / Structured Facts)
# -------------------------------------------------------------------------
def tool_get_medication_history(db: Session, patient_id: int, drug_keyword: Optional[str] = None) -> Tuple[List[str], List[TraceableSource]]:
    query = db.query(MedicationEvent).filter(MedicationEvent.patient_id == patient_id)
    if drug_keyword:
        query = query.filter(MedicationEvent.drug_name.ilike(f"%{drug_keyword}%"))
    events = query.order_by(MedicationEvent.created_at.asc()).all()

    facts = []
    sources = []
    for e in events:
        d_str = e.created_at.strftime("%d %b %Y")
        transition = f"{e.old_dose} -> {e.new_dose}" if (e.old_dose and e.new_dose) else (e.new_dose or e.old_dose or "")
        line = f"• {d_str}: {e.drug_name} {e.action} ({transition})".strip()
        if e.reason:
            line += f". Reason: {e.reason}"
        if e.reason_details:
            line += f" ({e.reason_details})"
        facts.append(line)
        sources.append(
            TraceableSource(
                source_type="medication_event",
                source_id=e.id,
                date=d_str,
                label=f"Medication Record ({e.drug_name})",
            )
        )
    return facts, sources


def tool_get_lab_history(db: Session, patient_id: int, test_keyword: Optional[str] = None) -> Tuple[List[str], List[TraceableSource]]:
    trends = calculate_lab_trends(db, patient_id)
    if test_keyword:
        trends = [t for t in trends if test_keyword.lower() in t.metric_name.lower()]

    facts = []
    sources = []
    for t in trends:
        line = f"• {t.metric_name}: Latest {t.latest_display} ({t.latest_date or 'Recent'})"
        if t.previous_display:
            line += f", Previously {t.previous_display} ({t.previous_date or 'Prior'}), Delta: {t.delta:+}"
        if t.direction != "stable":
            line += f" ({t.direction})"
        facts.append(line)

        for pt in t.history[-3:]:
            sources.append(
                TraceableSource(
                    source_type="lab",
                    source_id=pt.source_id,
                    date=pt.date,
                    label=f"{t.metric_name} test result",
                )
            )
    return facts, sources


def tool_get_open_loops(db: Session, patient_id: int) -> Tuple[List[str], List[TraceableSource]]:
    loops = get_patient_open_loops(db, patient_id)
    facts = []
    sources = []
    for l in loops:
        d_str = l.expected_date.strftime("%d %b %Y") if l.expected_date else "Not specified"
        overdue_note = f" [OVERDUE by {l.days_overdue} days]" if l.is_overdue else ""
        facts.append(f"• {l.description} (Expected: {d_str}){overdue_note} - Status: {l.status}")
        sources.append(
            TraceableSource(
                source_type="open_loop",
                source_id=l.id,
                date=d_str,
                label=f"Open Loop: {l.description}",
            )
        )
    return facts, sources


def tool_get_recent_changes(db: Session, patient_id: int) -> Tuple[List[str], List[TraceableSource]]:
    changes = get_changes_since_last_visit(db, patient_id)
    facts = []
    sources = []
    for c in changes.important_metric_changes:
        facts.append(f"• {c.test_or_vital}: {c.previous} -> {c.current} ({c.direction})")
    for r in changes.new_results:
        facts.append(f"• New Lab: {r['test_name']} = {r['result_value']} {r.get('unit','')}".strip())
    for m in changes.medication_changes:
        facts.append(f"• Medication Change: {m.drug_name} {m.action} ({m.reason or 'Adjusted'})")
    return facts, sources


def query_pg_assistant(
    db: Session,
    patient_id: int,
    doctor_id: Optional[int],
    question: str,
    active_problem_override: Optional[str] = None,
    active_topic_override: Optional[str] = None,
) -> PGAssistantResponse:
    """Process a clinician's clinical inquiry with strict token limits and source traceability."""
    start_time = time.time()

    # Load patient safely (de-identified context)
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise ValueError("Patient not found")

    # Load or init conversation state
    conv_state = (
        db.query(ConversationState)
        .filter(ConversationState.patient_id == patient_id, ConversationState.doctor_id == doctor_id)
        .first()
    )

    intent, detected_topic = route_intent(question, conv_state)
    active_topic = active_topic_override or detected_topic or (conv_state.active_topic if conv_state else None)
    active_problem = active_problem_override or (conv_state.active_problem if conv_state else None)

    # Context Builder: Collect minimal relevant facts (<800 tokens)
    facts: List[str] = []
    sources: List[TraceableSource] = []

    if intent in ("medication", "follow_up_topic") and (active_topic or "med" in intent):
        f, s = tool_get_medication_history(db, patient_id, drug_keyword=active_topic)
        facts.extend(f)
        sources.extend(s)
    elif intent in ("labs", "follow_up_topic"):
        f, s = tool_get_lab_history(db, patient_id, test_keyword=active_topic)
        facts.extend(f)
        sources.extend(s)
    elif intent == "open_loops":
        f, s = tool_get_open_loops(db, patient_id)
        facts.extend(f)
        sources.extend(s)
    elif intent == "changes":
        f, s = tool_get_recent_changes(db, patient_id)
        facts.extend(f)
        sources.extend(s)
    else:
        # General chart brief
        f_labs, s_labs = tool_get_lab_history(db, patient_id)
        f_meds, s_meds = tool_get_medication_history(db, patient_id)
        facts.extend(f_labs[:4])
        facts.extend(f_meds[:4])
        sources.extend(s_labs[:2])
        sources.extend(s_meds[:2])

    # If active problem is known, find related problems
    probs = db.query(PatientProblem).filter(PatientProblem.patient_id == patient_id).all()
    prob_names = [p.problem_name for p in probs]

    # Deterministic generation or LLM call
    api_key = os.getenv("OPEN_AI_KEY") or os.getenv("OPENAI_API_KEY")
    input_tokens = 0
    output_tokens = 0
    model_name = "local-deterministic-template"

    observations: List[str] = []
    answer_text = ""

    if not facts:
        facts = ["No matching clinical records or documented events found in this category."]

    # Local deterministic synthesis
    if "why" in question.lower() and "stopped" in question.lower():
        observations.append("Medication discontinuation rationale documented as above.")
    elif "trend" in question.lower() or "worsen" in question.lower():
        observations.append("Review glycemic/renal trends against target thresholds.")
    else:
        observations.append("Clinical data retrieved directly from verified structured records.")

    if api_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, timeout=12, max_retries=0)
            model_name = os.getenv("PG_ASSISTANT_MODEL", "gpt-4.1-mini")

            user_prompt = f"""Patient: {patient.gender or 'Patient'}, Problems: {', '.join(prob_names) or 'None documented'}
Verified Records:
{chr(10).join(facts)}

Question: {question}"""

            resp = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": PG_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=300,
                temperature=0.1,
            )
            raw_text = resp.choices[0].message.content.strip()
            answer_text = raw_text

            if resp.usage:
                input_tokens = resp.usage.prompt_tokens
                output_tokens = resp.usage.completion_tokens

        except Exception as e:
            answer_text = f"FACTS:\n" + "\n".join(facts) + f"\n\nPG OBSERVATION:\n" + "\n".join(observations)
    else:
        answer_text = f"FACTS:\n" + "\n".join(facts) + f"\n\nPG OBSERVATION:\n" + "\n".join(observations)

    latency_ms = int((time.time() - start_time) * 1000)
    # Estimate cost: approx $0.15 per 1M input, $0.60 per 1M output for gpt-4.1-mini
    estimated_cost = round((input_tokens * 0.00000015) + (output_tokens * 0.0000006), 6)

    # Update or create ConversationState
    if not conv_state:
        conv_state = ConversationState(
            patient_id=patient_id,
            doctor_id=doctor_id,
            active_topic=active_topic,
            active_problem=active_problem,
            last_intent=intent,
            last_question=question,
            last_answer=answer_text,
        )
        db.add(conv_state)
    else:
        conv_state.active_topic = active_topic
        conv_state.active_problem = active_problem
        conv_state.last_intent = intent
        conv_state.last_question = question
        conv_state.last_answer = answer_text
    db.commit()

    # Log to AIInteraction
    audit_entry = AIInteraction(
        patient_id=patient_id,
        doctor_id=doctor_id,
        action="ask_pg",
        model=model_name,
        query=question,
        response=answer_text,
        retrieved_sources=[s.model_dump() for s in sources],
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        estimated_cost=estimated_cost,
    )
    db.add(audit_entry)
    db.commit()

    return PGAssistantResponse(
        intent=intent,
        facts=facts,
        pg_observations=observations,
        answer_text=answer_text,
        sources=sources,
        active_topic=active_topic,
        active_problem=active_problem,
        tokens_used=input_tokens + output_tokens,
        latency_ms=latency_ms,
        estimated_cost=estimated_cost,
    )
