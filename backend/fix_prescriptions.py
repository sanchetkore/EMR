from app.core.database import SessionLocal
from app.models.prescription import Prescription
from app.models.encounter import Encounter
import datetime

def fix_prescriptions():
    db = SessionLocal()
    try:
        unlinked_prescriptions = db.query(Prescription).filter(Prescription.encounter_id == None).all()
        print(f"Found {len(unlinked_prescriptions)} unlinked prescriptions.")
        
        for p in unlinked_prescriptions:
            # Find closest encounter for this patient
            encounter = db.query(Encounter).filter(
                Encounter.patient_id == p.patient_id
            ).order_by(Encounter.encounter_date.desc()).first()
            
            if encounter:
                p.encounter_id = encounter.id
                print(f"Linked prescription {p.id} to encounter {encounter.id}")
        
        db.commit()
        print("Done.")
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    fix_prescriptions()
