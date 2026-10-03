"""Appointment scoping must happen before any clinical-record scans."""
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@127.0.0.1:1/emr_test')

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import app.models
from app.core.database import Base
from app.models.patient import Patient, Appointment
from app.services.attention_engine import get_clinic_attention_queue


class AttentionQueuePaginationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.day = datetime.now(timezone(timedelta(hours=5, minutes=30))).date()
        self.start = datetime.combine(self.day, datetime.min.time())
        for patient_id in range(1, 10):
            self.db.add(Patient(id=patient_id, first_name=f'Patient {patient_id}', last_name='',
                                is_active=0 if patient_id == 8 else 1))
        fixtures = [
            (1, self.start, 'Scheduled'),
            (1, self.start + timedelta(hours=1), 'Scheduled'),
            (2, self.start + timedelta(hours=2), 'Completed'),
            (3, self.start + timedelta(days=1) - timedelta(microseconds=1), 'Scheduled'),
            (4, self.start - timedelta(microseconds=1), 'Scheduled'),
            (5, self.start + timedelta(days=1), 'Scheduled'),
            (6, self.start, 'Cancelled'),
            (7, self.start, 'No Show'),
            (8, self.start, 'Scheduled'),
        ]
        for pid, time, status in fixtures:
            self.db.add(Appointment(patient_id=pid, appointment_time=time, status=status, doctor_id=pid))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    @patch('app.services.attention_engine.get_patient_attention_items')
    def test_pages_scan_only_distinct_eligible_patients(self, scan):
        scan.return_value = {'needs_decision': [], 'needs_attention': [], 'fyi': []}
        first = get_clinic_attention_queue(self.db, page=1, page_size=2)
        self.assertEqual([call.args[1] for call in scan.call_args_list], [1, 2])
        self.assertEqual(first.total_patients, 3)
        self.assertEqual(first.scanned_patients, 2)
        self.assertEqual(first.total_count, 0)
        self.assertTrue(first.has_next)
        self.assertEqual(first.appointment_date, self.day)
        scan.reset_mock()
        last = get_clinic_attention_queue(self.db, page=2, page_size=2)
        self.assertEqual([call.args[1] for call in scan.call_args_list], [3])
        self.assertFalse(last.has_next)
        scan.reset_mock()
        empty = get_clinic_attention_queue(self.db, page=3, page_size=2)
        scan.assert_not_called()
        self.assertEqual(empty.scanned_patients, 0)

    @patch('app.services.attention_engine.get_patient_attention_items')
    def test_doctor_filter_and_no_appointments(self, scan):
        scan.return_value = {'needs_decision': [], 'needs_attention': [], 'fyi': []}
        queue = get_clinic_attention_queue(self.db, doctor_id=2)
        self.assertEqual(queue.total_patients, 1)
        self.assertEqual(scan.call_args.args[1], 2)
        scan.reset_mock()
        queue = get_clinic_attention_queue(self.db, doctor_id=999)
        self.assertEqual(queue.total_patients, 0)
        scan.assert_not_called()

    def test_invalid_pagination(self):
        for page, size in [(0, 20), (1, 0), (1, 51)]:
            with self.assertRaises(ValueError):
                get_clinic_attention_queue(self.db, page=page, page_size=size)
