"""Check same-day booking behavior with actual SQLAlchemy queries."""

import ast
from datetime import datetime, timedelta
import os
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@127.0.0.1:1/emr_test")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import BackgroundTasks, Depends, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models
from app.core.database import Base
from app.models.patient import Appointment
from app.schemas.patient import AppointmentCreate
from app.models.settings import SystemSetting
from app.services.clinic_closures import ClinicClosures, closure_reason
from pydantic import ValidationError


def load_create_appointment():
    path = Path(__file__).resolve().parents[1] / "app/api/appointments.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node = next(node for node in tree.body if getattr(node, "name", "") == "create_appointment")
    node.decorator_list = []
    namespace = {
        "AppointmentCreate": AppointmentCreate, "Appointment": Appointment,
        "BackgroundTasks": BackgroundTasks, "Session": Session,
        "Depends": Depends, "get_db": lambda: None,
        "datetime": datetime, "timedelta": timedelta,
        "HTTPException": HTTPException, "get_live_queue": lambda db: {},
        "manager": SimpleNamespace(broadcast=lambda payload: None),
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace["create_appointment"]


class AppointmentBookingTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add(Appointment(patient_id=1, doctor_id=2, appointment_time=datetime(2026, 9, 29, 10, 0), status="Scheduled", token_number="001"))
        self.db.commit()
        self.create = load_create_appointment()
        self.background = SimpleNamespace(add_task=lambda *args, **kwargs: None)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_same_day_different_doctor_is_allowed(self):
        result = self.create(AppointmentCreate(patient_id=1, doctor_id=3, appointment_time=datetime(2026, 9, 29, 10, 0)), self.background, self.db)
        self.assertEqual(result.doctor_id, 3)

    def test_weekly_holiday_blocks_booking(self):
        self.db.add(SystemSetting(key='clinic_closures', value='{"weekly_days_off":[2],"holidays":[]}'))
        self.db.commit()
        with self.assertRaises(HTTPException) as error:
            self.create(AppointmentCreate(patient_id=1, doctor_id=3, appointment_time=datetime(2026, 9, 29, 10)), self.background, self.db)
        self.assertEqual(error.exception.status_code, 409)
        self.assertIn('Weekly holiday', error.exception.detail)

    def test_named_holiday_blocks_booking_and_preserves_existing(self):
        self.db.add(SystemSetting(key='clinic_closures', value='{"weekly_days_off":[],"holidays":[{"date":"2026-09-29","name":"Clinic holiday"}]}'))
        self.db.commit()
        with self.assertRaises(HTTPException) as error:
            self.create(AppointmentCreate(patient_id=1, doctor_id=3, appointment_time=datetime(2026, 9, 29, 11)), self.background, self.db)
        self.assertIn('Clinic holiday', error.exception.detail)
        self.assertEqual(self.db.query(Appointment).count(), 1)
        result = self.create(AppointmentCreate(patient_id=1, doctor_id=3, appointment_time=datetime(2026, 9, 30, 11)), self.background, self.db)
        self.assertEqual(result.appointment_time.day, 30)

    def test_sunday_numbering_and_holiday_validation(self):
        self.db.add(SystemSetting(key='clinic_closures', value='{"weekly_days_off":[0],"holidays":[]}'))
        self.db.commit()
        self.assertEqual(closure_reason(self.db, datetime(2026, 10, 4).date()), 'Weekly holiday')
        self.assertIsNone(closure_reason(self.db, datetime(2026, 10, 5).date()))
        with self.assertRaises(ValidationError):
            ClinicClosures(weekly_days_off=[7])
        with self.assertRaises(ValidationError):
            ClinicClosures(holidays=[{'date': 'invalid', 'name': 'Holiday'}])

    def test_same_patient_doctor_and_minute_is_rejected(self):
        with self.assertRaises(HTTPException) as error:
            self.create(AppointmentCreate(patient_id=1, doctor_id=2, appointment_time=datetime(2026, 9, 29, 10, 0, 30)), self.background, self.db)
        self.assertEqual(error.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
