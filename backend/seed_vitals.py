import sys
import os

# Ensure we can import from app
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.core.database import SessionLocal
from app.models.encounter import VitalConfiguration

vitals = [
    {
        "name": "Blood Pressure",
        "data_type": "string",
        "formula": None,
        "is_active": True,
        "id": 1
    },
    {
        "name": "Temperature",
        "data_type": "float",
        "formula": None,
        "is_active": True,
        "id": 2
    },
    {
        "name": "Heart Rate",
        "data_type": "integer",
        "formula": None,
        "is_active": True,
        "id": 3
    },
    {
        "name": "Height (cm)",
        "data_type": "float",
        "formula": None,
        "is_active": True,
        "id": 4
    },
    {
        "name": "Weight (kg)",
        "data_type": "float",
        "formula": None,
        "is_active": True,
        "id": 5
    },
    {
        "name": "BMI",
        "data_type": "computed",
        "formula": "Weight (kg) / ((Height (cm)/100) * (Height (cm)/100))",
        "is_active": True,
        "id": 6
    }
]

def seed_vitals():
    db = SessionLocal()
    try:
        for v in vitals:
            existing = db.query(VitalConfiguration).filter(VitalConfiguration.id == v['id']).first()
            if not existing:
                new_vital = VitalConfiguration(**v)
                db.add(new_vital)
            else:
                existing.name = v['name']
                existing.data_type = v['data_type']
                existing.formula = v['formula']
                existing.is_active = v['is_active']
        db.commit()
        print("Successfully seeded vitals!")
    except Exception as e:
        print(f"Error seeding vitals: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_vitals()
