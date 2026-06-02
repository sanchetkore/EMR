from app.core.database import SessionLocal
from app.models.patient import AppointmentStatusConfig, AppointmentTypeConfig

db = SessionLocal()
statuses = db.query(AppointmentStatusConfig).all()
types = db.query(AppointmentTypeConfig).all()

print("STATUSES:")
for s in statuses:
    print(f"ID: {s.id}, Name: {s.name}")

print("\nTYPES:")
for t in types:
    print(f"ID: {t.id}, Name: {t.name}")

db.close()
