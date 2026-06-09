import os
from openai import OpenAI
from sqlalchemy.orm import Session
from app.models.patient import PatientAISummary

def get_openai_client():
    api_key = os.getenv("OPEN_AI_KEY")
    if not api_key:
        print("Warning: OPEN_AI_KEY environment variable is missing. AI features will be disabled.")
        return None
    return OpenAI(api_key=api_key)

def generate_updated_summary(existing_summary: str, new_data_note: str) -> str:
    client = get_openai_client()
    if not client:
        return existing_summary
    system_prompt = """You are an expert clinical AI assistant. Your task is to update a patient's master medical summary based on a new clinical visit note.
You will be provided with:
1. EXISTING SUMMARY: The patient's current master summary before today's visit.
2. NEW VISIT NOTE: The doctor's notes from today's visit or todays lab report
Follow these strict rules:
- RETAIN all chronic conditions, major historical surgeries, and long-term medications from the EXISTING SUMMARY.
- INTEGRATE any new diagnoses, significant medication changes, or critical lab results from the NEW VISIT NOTE.
- REMOVE or mark as resolved any minor, acute, or temporary issues from the EXISTING SUMMARY that are no longer relevant (e.g., past common colds, healed minor fractures).
- FORMAT the output as a concise, bulleted list. Do not write full paragraphs. 
- KEEP IT SHORT. The final output must not exceed 150 words.
- STRICTLY DO NOT invent or hallucinate any medical information. If the text does not explicitly state it, do not include it."""

    user_message = f"""EXISTING SUMMARY:
{existing_summary or 'No existing summary.'}

NEW VISIT NOTE:
{new_data_note}"""

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            max_tokens=300,
            temperature=0.2
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error calling OpenAI API: {e}")
        return existing_summary

def process_and_save_ai_summary(patient_id: int, new_data_str: str, db: Session):
    # Fetch existing summary
    db_summary = db.query(PatientAISummary).filter(PatientAISummary.patient_id == patient_id).first()
    existing_text = db_summary.summary_text if db_summary else ""
    
    # Generate new summary
    new_text = generate_updated_summary(existing_text, new_data_str)
    
    # Save or update summary
    if db_summary:
        if new_text and new_text != existing_text:
            db_summary.summary_text = new_text
            db.commit()
    else:
        if new_text:
            db_summary = PatientAISummary(patient_id=patient_id, summary_text=new_text)
            db.add(db_summary)
            db.commit()

from app.core.database import SessionLocal
import threading
from datetime import datetime

_lab_summary_timers = {}
_timer_lock = threading.Lock()

def schedule_lab_ai_summary(patient_id: int):
    with _timer_lock:
        if patient_id in _lab_summary_timers:
            _lab_summary_timers[patient_id].cancel()
        
        timer = threading.Timer(10.0, execute_lab_ai_summary, args=[patient_id])
        _lab_summary_timers[patient_id] = timer
        timer.start()

def execute_lab_ai_summary(patient_id: int):
    with _timer_lock:
        if patient_id in _lab_summary_timers:
            del _lab_summary_timers[patient_id]
            
    db = SessionLocal()
    try:
        from app.models.lab_result import LabResult
        import json
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        
        todays_labs = db.query(LabResult).filter(
            LabResult.patient_id == patient_id,
            LabResult.status == "Completed",
            LabResult.result_date >= today_start
        ).all()
        
        if not todays_labs:
            return
            
        lab_details = []
        for lab in todays_labs:
            lab_details.append({
                "test_name": lab.test_name,
                "result_value": lab.result_value,
                "unit": lab.unit,
                "reference_range": lab.reference_range,
                "notes": lab.notes
            })
            
        new_data_str = f"Lab Test Date: {datetime.utcnow().date()}\n" + json.dumps(lab_details, indent=2)
        process_and_save_ai_summary(patient_id, new_data_str, db)
    except Exception as e:
        print(f"Failed to process delayed AI summary: {e}")
    finally:
        db.close()

def background_ai_summary_task(patient_id: int, new_data_str: str):
    db = SessionLocal()
    try:
        process_and_save_ai_summary(patient_id, new_data_str, db)
    except Exception as e:
        print(f"Failed to process AI summary: {e}")
    finally:
        db.close()
