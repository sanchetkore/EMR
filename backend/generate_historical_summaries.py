import os
import sys
from dotenv import load_dotenv

# Ensure we can import app modules
sys.path.append(os.path.dirname(__file__))
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'), override=True)
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'), override=True)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.patient import Patient, Appointment, PatientAISummary
from app.models.encounter import Encounter, VisitComplaint, VisitDiagnosis, VisitTreatment, PatientVital
from app.models.lab_result import LabResult
from openai import OpenAI
import json

client = OpenAI(api_key=os.getenv("OPEN_AI_KEY"))

# Use DATABASE_URL from .env
engine = create_engine(os.getenv("DATABASE_URL"))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def generate_bulk_summary(history_text: str) -> str:
    system_prompt = """You are an expert clinical AI assistant. Your task is to create a master medical summary for a patient based on their complete historical medical records provided below. Extract all chronic conditions, major historical surgeries, long-term medications, significant diagnoses, and critical lab results. Format the output as a concise, bulleted list not exceeding 150 words."""

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": history_text}
            ],
            max_tokens=300,
            temperature=0.2
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error calling OpenAI API: {e}")
        return "Error generating summary."

def main():
    db = SessionLocal()
    patients = db.query(Patient).all()
    print(f"Found {len(patients)} total patients.")
    
    for patient in patients:
        # Check if summary already exists
        existing_summary = db.query(PatientAISummary).filter(PatientAISummary.patient_id == patient.id).first()
        if existing_summary:
            print(f"Skipping Patient #{patient.id} - Summary already exists.")
            continue
            
        # Fetch encounters
        encounters = db.query(Encounter).filter(Encounter.patient_id == patient.id, Encounter.status == "Completed").order_by(Encounter.encounter_date.asc()).all()
        # Fetch labs
        labs = db.query(LabResult).filter(LabResult.patient_id == patient.id, LabResult.status == "Completed").order_by(LabResult.result_date.asc()).all()
        
        if not encounters and not labs:
            print(f"Patient #{patient.id} has no history. Setting 'First Time'.")
            db_summary = PatientAISummary(patient_id=patient.id, summary_text="First Time")
            db.add(db_summary)
            db.commit()
            continue
            
        history_parts = []
        for enc in encounters:
            complaints = [c.complaint for c in db.query(VisitComplaint).filter(VisitComplaint.encounter_id == enc.id).all() if c.complaint]
            diagnoses = [d.diagnosis for d in db.query(VisitDiagnosis).filter(VisitDiagnosis.encounter_id == enc.id).all() if d.diagnosis]
            treatments = [t.treatment for t in db.query(VisitTreatment).filter(VisitTreatment.encounter_id == enc.id).all() if t.treatment]
            
            history_parts.append(
                f"Visit on {enc.encounter_date.date() if enc.encounter_date else 'Unknown'}:\n"
                f"- Complaints: {', '.join(complaints)}\n"
                f"- Diagnoses: {', '.join(diagnoses)}\n"
                f"- Treatments: {', '.join(treatments)}\n"
                f"- Notes: {enc.notes}"
            )
            
        for lab in labs:
            history_parts.append(
                f"Lab Test on {lab.result_date.date() if lab.result_date else 'Unknown'}:\n"
                f"- Test: {lab.test_name}\n"
                f"- Result: {lab.result_value} {lab.unit} (Range: {lab.reference_range})\n"
                f"- Notes: {lab.notes}"
            )
            
        full_history = "\n\n".join(history_parts)
        print(f"Generating summary for Patient #{patient.id}...")
        
        summary_text = generate_bulk_summary(full_history)
        
        db_summary = PatientAISummary(patient_id=patient.id, summary_text=summary_text)
        db.add(db_summary)
        db.commit()
        print(f"Saved summary for Patient #{patient.id}")

    db.close()
    print("Done!")

if __name__ == "__main__":
    main()
