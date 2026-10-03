"""Unsigned prescription drafts must not reach the public dispensing queue."""
import ast
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys
import unittest
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@127.0.0.1:1/emr_test')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine, or_
from sqlalchemy.orm import Session, joinedload
import app.models
from app.core.database import Base
from app.models.encounter import Encounter
from app.models.patient import Appointment
from app.models.prescription import Prescription


class DraftQueueTests(unittest.TestCase):
    def test_draft_is_hidden_then_appears_after_signing(self):
        path = Path(__file__).resolve().parents[1] / 'app/api/queue.py'
        node = next(n for n in ast.parse(path.read_text(encoding='utf-8')).body if getattr(n, 'name', '') == 'get_live_queue')
        namespace = dict(Session=Session, datetime=datetime, timedelta=timedelta, timezone=timezone,
                         Appointment=Appointment, Prescription=Prescription, Encounter=Encounter,
                         joinedload=joinedload, or_=or_)
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), namespace)
        engine = create_engine('sqlite://')
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            encounter = Encounter(patient_id=1, doctor_id=1, status='Ongoing', visit_number=1)
            db.add(encounter)
            db.flush()
            now = datetime.now(timezone(timedelta(hours=5, minutes=30))).replace(tzinfo=None)
            prescription = Prescription(encounter_id=encounter.id, patient_id=1, doctor_id=1, status='Pending', date_prescribed=now)
            db.add(prescription)
            db.commit()
            self.assertEqual(namespace['get_live_queue'](db)['pharmacy_waiting'], [])
            encounter.status = 'Completed'
            db.commit()
            rows = namespace['get_live_queue'](db)['pharmacy_waiting']
            self.assertEqual([row['prescription_id'] for row in rows], [prescription.id])
        engine.dispose()
