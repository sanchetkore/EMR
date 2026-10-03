"""AI-Assisted Plan Structuring Service.
Parses short unstructured doctor instructions into candidate structured actions.
Requires explicit doctor confirmation before persisting to the database.
"""
import re
import os
import json
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.models.encounter import Encounter
from app.models.patient_brain import OpenLoop, ClinicalDecision, ClinicalEvent
from app.schemas.patient_brain import PlanActionItem, PlanStructureResponse
from app.services.open_loops_engine import create_open_loop
from app.services.why_memory_service import record_clinical_decision


PLAN_EXTRACTION_PROMPT = """Extract clinical plan actions from the doctor's free-text plan.
Return a valid JSON object with an 'actions' list.
Each action must have:
- 'type': one of ['continue_medication', 'change_medication', 'stop_medication', 'investigation', 'referral', 'follow_up']
- 'description': brief clear human readable summary
- 'drug_name': drug name if applicable or null
- 'dose': dose if applicable or null
- 'test_name': lab or imaging test name if applicable or null
- 'due_in': timeframe string (e.g. '3 months', '2 weeks', '1 month') or null
- 'expected_days': integer approximate days from today (e.g. 90 for 3 months) or null

Do not invent tests or medications that were not mentioned in the doctor's text."""


def extract_plan_actions_deterministic(text: str) -> List[PlanActionItem]:
    """Rule-based plan extraction fallback when AI provider is unavailable."""
    actions: List[PlanActionItem] = []
    t = text.lower()

    # Continue meds
    if "continue" in t:
        med_match = re.search(r"continue\s+([a-zA-Z0-9\s]+?)(?=\.|,|and|repeat|review|$)", t)
        desc = med_match.group(0).strip().capitalize() if med_match else "Continue current medications"
        actions.append(PlanActionItem(type="continue_medication", description=desc))

    # Investigations
    tests = [
        ("hba1c", "HbA1c"),
        ("creatinine", "Serum Creatinine"),
        ("cbc", "Complete Blood Count (CBC)"),
        ("lft", "Liver Function Test (LFT)"),
        ("kft", "Kidney Function Test (KFT)"),
        ("lipid", "Lipid Profile"),
        ("mri", "MRI"),
        ("ct", "CT Scan"),
        ("xray", "X-Ray"),
        ("ecg", "ECG"),
        ("echo", "Echocardiogram"),
        ("usg", "USG Abdomen"),
    ]
    for key, label in tests:
        if key in t:
            # Check for due duration
            dur_match = re.search(rf"(?:after|in)?\s*(\d+)\s*(month|week|day)s?", t)
            due_in = None
            days = 30
            if dur_match:
                num = int(dur_match.group(1))
                unit = dur_match.group(2)
                due_in = f"{num} {unit}s"
                days = num * (30 if unit == "month" else (7 if unit == "week" else 1))

            actions.append(
                PlanActionItem(
                    type="investigation",
                    description=f"Repeat {label}" if "repeat" in t else f"Order {label}",
                    test_name=label,
                    due_in=due_in or "3 months",
                    expected_days=days,
                )
            )

    # Referral
    if "refer" in t or "consult" in t:
        ref_match = re.search(r"(?:refer|referral\s+to|consult)\s+([a-zA-Z]+)", t)
        spec = ref_match.group(1).capitalize() if ref_match else "Specialist"
        actions.append(
            PlanActionItem(
                type="referral",
                description=f"{spec} referral",
                due_in="2 weeks",
                expected_days=14,
            )
        )

    # Follow up / review
    if any(k in t for k in ["review", "follow up", "f/u", "visit again"]):
        dur_match = re.search(r"(\d+)\s*(month|week|day)s?", t)
        due_in = "1 month"
        days = 30
        if dur_match:
            num = int(dur_match.group(1))
            unit = dur_match.group(2)
            due_in = f"{num} {unit}s"
            days = num * (30 if unit == "month" else (7 if unit == "week" else 1))

        actions.append(
            PlanActionItem(
                type="follow_up",
                description=f"Follow-up and clinical review in {due_in}",
                due_in=due_in,
                expected_days=days,
            )
        )

    return actions


def parse_plan_text(text: str) -> PlanStructureResponse:
    """Parse clinician's short notes into structured action items."""
    api_key = os.getenv("OPEN_AI_KEY") or os.getenv("OPENAI_API_KEY")
    actions: List[PlanActionItem] = []

    if api_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, timeout=10, max_retries=0)
            resp = client.chat.completions.create(
                model=os.getenv("PLAN_STRUCTURING_MODEL", "gpt-4.1-mini"),
                messages=[
                    {"role": "system", "content": PLAN_EXTRACTION_PROMPT},
                    {"role": "user", "content": text}
                ],
                response_format={"type": "json_object"},
                temperature=0,
            )
            data = json.loads(resp.choices[0].message.content)
            for item in data.get("actions", []):
                actions.append(PlanActionItem(**item))
        except Exception:
            actions = extract_plan_actions_deterministic(text)
    else:
        actions = extract_plan_actions_deterministic(text)

    # Generate readable summary preview
    summary = []
    for a in actions:
        timeframe = f" ({a.due_in})" if a.due_in else ""
        summary.append(f"• {a.description}{timeframe}")

    return PlanStructureResponse(
        raw_text=text,
        actions=actions,
        summary_preview=summary,
    )


def commit_plan_actions(
    db: Session,
    patient_id: int,
    visit_id: Optional[int],
    doctor_id: Optional[int],
    actions: List[PlanActionItem],
) -> Dict[str, Any]:
    """Persist doctor-confirmed structured plan items into ClinicalDecisions and OpenLoops."""
    created_loops = []
    created_decisions = []
    today = date.today()

    for a in actions:
        # 1. Clinical Decision
        dec = record_clinical_decision(
            db=db,
            patient_id=patient_id,
            decision=a.description,
            reason="Confirmed Consultation Plan",
            doctor_id=doctor_id,
            visit_id=visit_id,
        )
        created_decisions.append(dec.id)

        # 2. Open Loops for future expectations
        if a.type in ("investigation", "referral", "follow_up"):
            days = a.expected_days or 30
            exp_date = today + timedelta(days=days)
            loop = create_open_loop(
                db=db,
                patient_id=patient_id,
                loop_type=a.type,
                description=a.description,
                expected_date=exp_date,
                target_code=a.test_name.upper() if a.test_name else None,
                source_visit_id=visit_id,
            )
            created_loops.append(loop.id)

    # If an encounter is provided, update followup days
    if visit_id:
        enc = db.query(Encounter).filter(Encounter.id == visit_id).first()
        if enc:
            followup_action = next((a for a in actions if a.type == "follow_up"), None)
            if followup_action and followup_action.expected_days:
                enc.followup_days = followup_action.expected_days
                enc.followup_date = today + timedelta(days=followup_action.expected_days)
                db.commit()

    return {
        "status": "committed",
        "decisions_created": len(created_decisions),
        "open_loops_created": len(created_loops),
    }
