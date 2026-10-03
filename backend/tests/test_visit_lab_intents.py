"""The persisted LIS request survives retries and is delivered once."""

import os
from pathlib import Path
import sys
import unittest
from datetime import datetime, timedelta

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@127.0.0.1:1/emr_test")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models
from app.core.database import Base
from app.models.visit_lab_intent import VisitLabOrderIntent
from app.services.lis_order_intents import process_lab_intent


class LabIntentDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.intent = VisitLabOrderIntent(
            encounter_id=1, patient_id=1, requested_by_id=1,
            source_id="visit-1", connection_id="lis-clinic-a",
            test_codes=["CBC"], package_codes=[], status="PENDING",
        )
        self.db.add(self.intent)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_success_is_not_submitted_twice(self):
        calls = []

        def submit(intent, db):
            calls.append((intent.source_id, intent.connection_id, intent.test_codes))
            return {"id": "order-1", "accessionNumber": "ACC-1"}

        first = process_lab_intent(self.db, self.intent.id, submit_order=submit)
        second = process_lab_intent(self.db, self.intent.id, force=True, submit_order=submit)
        self.assertEqual(calls, [("visit-1", "lis-clinic-a", ["CBC"])])
        self.assertEqual(first.status, "ACCEPTED")
        self.assertEqual(second.accession_number, "ACC-1")
        self.assertEqual(second.attempt_count, 1)

    def test_failure_retries_with_same_request_identity(self):
        def unavailable(intent, db):
            raise HTTPException(status_code=503, detail="LIS unavailable")

        failed = process_lab_intent(self.db, self.intent.id, submit_order=unavailable)
        self.assertEqual(failed.status, "FAILED")
        self.assertEqual(failed.attempt_count, 1)
        self.assertIsNotNone(failed.retry_after)
        self.assertEqual(process_lab_intent(self.db, self.intent.id, submit_order=unavailable).attempt_count, 1)

        received = []
        recovered = process_lab_intent(
            self.db, self.intent.id, force=True,
            submit_order=lambda intent, db: received.append(intent.source_id) or {"id": "order-1"},
        )
        self.assertEqual(received, ["visit-1"])
        self.assertEqual(recovered.status, "ACCEPTED")
        self.assertEqual(recovered.attempt_count, 2)

    def test_expired_lease_can_be_reclaimed(self):
        self.intent.status = "PROCESSING"
        self.intent.lease_expires_at = datetime.utcnow() - timedelta(seconds=1)
        self.db.commit()
        result = process_lab_intent(self.db, self.intent.id, submit_order=lambda intent, db: {"id": "order-1"})
        self.assertEqual(result.status, "ACCEPTED")


if __name__ == "__main__":
    unittest.main()
