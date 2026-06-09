import os, sys
from dotenv import load_dotenv
load_dotenv('.env')

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
sys.path.append('C:\\Users\\sanch\\OneDrive\\Documents\\EMR\\backend')
from app.models.patient import Appointment, Patient

# Need to replace env vars manually as dotenv doesn't do interpolation by default
db_url = os.getenv('DATABASE_URL')
if '${POSTGRES_USER}' in db_url:
    db_url = db_url.replace('${POSTGRES_USER}', os.getenv('POSTGRES_USER')).replace('${POSTGRES_PASSWORD}', os.getenv('POSTGRES_PASSWORD')).replace('${POSTGRES_DB}', os.getenv('POSTGRES_DB'))

engine = create_engine(db_url)
Session = sessionmaker(bind=engine)
db = Session()

# Find John Doe
patient = db.query(Patient).filter(Patient.first_name.ilike('%John%'), Patient.last_name.ilike('%Doe%')).first()
if not patient:
    print('Patient not found')
else:
    print(f'Patient found: {patient.id} - {patient.first_name} {patient.last_name}')
    appts = db.query(Appointment).filter(Appointment.patient_id == patient.id).order_by(Appointment.appointment_time.asc()).all()
    for a in appts:
        print(f'Appt ID: {a.id}, Time: {a.appointment_time}, Status: \"{a.status}\"')
