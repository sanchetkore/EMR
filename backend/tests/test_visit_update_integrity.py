"""Exercise visit update persistence and rollback against real SQLite models."""

import ast
import logging
import os
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@127.0.0.1:1/emr_test")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import BackgroundTasks, Depends, HTTPException
from sqlalchemy import create_engine, event, func
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models
from app.core.database import Base
from app.models.encounter import Encounter, EncounterAmendment, PatientVital, VisitComplaint, VisitDiagnosis, VisitTreatment
from app.models.lab_result import LabResult, LabCatalog
from app.models.patient import Appointment
from app.models.prescription import Prescription, PrescriptionItem
from app.schemas.encounter import VisitPayload, VisitUpdate, AmendmentCreate
from app.schemas.prescription import PrescriptionCreate


def load_update_route():
    path = Path(__file__).resolve().parents[1] / "app/api/visits.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node = next(node for node in tree.body if getattr(node, "name", "") == "update_visit")
    node.decorator_list = []
    namespace = {
        "VisitUpdate": VisitUpdate, "BackgroundTasks": BackgroundTasks,
        "Depends": Depends, "get_db": lambda: None, "Session": Session,
        "RequirePermission": lambda permission: None, "User": object,
        "Encounter": Encounter, "PatientVital": PatientVital,
        "VisitComplaint": VisitComplaint, "VisitDiagnosis": VisitDiagnosis,
        "VisitTreatment": VisitTreatment, "LabResult": LabResult,
        "LabCatalog": LabCatalog, "Appointment": Appointment,
        "Prescription": Prescription, "PrescriptionItem": PrescriptionItem,
        "HTTPException": HTTPException, "timedelta": __import__("datetime").timedelta,
        "datetime": __import__("datetime").datetime,
        "get_live_queue": lambda db: {},
        "manager": SimpleNamespace(broadcast=lambda payload: None),
        "logger": logging.getLogger(__name__),
        "_build_visit_response": lambda encounter, db: encounter.id,
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace["update_visit"]


def load_create_route():
    path = Path(__file__).resolve().parents[1] / "app/api/visits.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node = next(node for node in tree.body if getattr(node, "name", "") == "create_visit")
    node.decorator_list = []
    namespace = {
        "VisitPayload": VisitPayload, "BackgroundTasks": BackgroundTasks,
        "Session": Session, "Depends": Depends, "get_db": lambda: None,
        "RequirePermission": lambda permission: None, "User": object,
        "Encounter": Encounter, "Appointment": Appointment,
        "PatientVital": PatientVital, "VisitComplaint": VisitComplaint,
        "VisitDiagnosis": VisitDiagnosis, "VisitTreatment": VisitTreatment,
        "LabCatalog": LabCatalog, "LabResult": LabResult,
        "Prescription": Prescription, "PrescriptionItem": PrescriptionItem,
        "func": func, "datetime": __import__("datetime").datetime,
        "timedelta": __import__("datetime").timedelta,
        "HTTPException": HTTPException, "logger": logging.getLogger(__name__),
        "get_live_queue": lambda db: {},
        "manager": SimpleNamespace(broadcast=lambda payload: None),
        "_build_visit_response": lambda encounter, db: encounter,
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace["create_visit"]


def load_amendment_route():
    path = Path(__file__).resolve().parents[1] / "app/api/visits.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node = next(node for node in tree.body if getattr(node, "name", "") == "add_visit_amendment")
    node.decorator_list = []
    namespace = {
        "AmendmentCreate": AmendmentCreate, "AmendmentSchema": object,
        "Depends": Depends, "RequirePermission": lambda permission: None,
        "get_db": lambda: None, "Session": Session, "User": object,
        "Encounter": Encounter, "EncounterAmendment": EncounterAmendment,
        "HTTPException": HTTPException,
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace["add_visit_amendment"]


def load_create_prescription_route():
    path = Path(__file__).resolve().parents[1] / "app/api/prescriptions.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node = next(node for node in tree.body if getattr(node, "name", "") == "create_prescription")
    node.decorator_list = []
    namespace = {
        "PrescriptionCreate": PrescriptionCreate, "BackgroundTasks": BackgroundTasks,
        "Session": Session, "Depends": Depends, "get_db": lambda: None,
        "Encounter": Encounter, "Prescription": Prescription,
        "PrescriptionItem": PrescriptionItem, "HTTPException": HTTPException,
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace["create_prescription"]


class VisitUpdateIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add(Encounter(id=1, patient_id=1, doctor_id=2, status="Open", notes="before"))
        self.db.add(VisitComplaint(encounter_id=1, complaint="old"))
        self.db.commit()
        self.update = load_update_route()
        self.create = load_create_route()
        self.amend = load_amendment_route()
        self.create_prescription = load_create_prescription_route()
        self.background = SimpleNamespace(add_task=lambda *args, **kwargs: None)
        self.clinician = SimpleNamespace(id=2)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_replaces_and_clears_clinical_collections(self):
        payload = VisitUpdate(
            expected_version=1, patient_id=1, doctor_id=2, notes="after",
            vitals=[{"vital_config_id": 4, "value": "120"}],
            complaints=[], diagnoses=[{"diagnosis": "New diagnosis"}],
            treatments=[{"treatment": "Rest"}],
        )
        self.update(1, payload, self.background, self.db, self.clinician)
        self.db.expire_all()
        self.assertEqual(self.db.get(Encounter, 1).notes, "after")
        self.assertEqual(self.db.get(Encounter, 1).version, 2)
        self.assertEqual(self.db.query(VisitComplaint).count(), 0)
        self.assertEqual(self.db.query(PatientVital).one().value, "120")
        self.assertEqual(self.db.query(VisitDiagnosis).one().diagnosis, "New diagnosis")
        self.assertEqual(self.db.query(VisitTreatment).one().treatment, "Rest")

    def test_later_write_failure_does_not_commit_earlier_changes(self):
        @event.listens_for(self.engine, "before_cursor_execute")
        def fail_diagnosis(conn, cursor, statement, parameters, context, executemany):
            if statement.startswith("INSERT INTO visit_diagnoses"):
                raise RuntimeError("simulated later write failure")

        with self.assertRaises(RuntimeError):
            self.update(1, VisitUpdate(expected_version=1, notes="should rollback", diagnoses=[{"diagnosis": "X"}]), self.background, self.db, self.clinician)
        self.db.rollback()
        self.db.expire_all()
        self.assertEqual(self.db.get(Encounter, 1).notes, "before")
        self.assertEqual(self.db.get(Encounter, 1).version, 1)
        self.assertEqual(self.db.query(VisitComplaint).one().complaint, "old")

    def test_rejects_identity_changes(self):
        with self.assertRaises(HTTPException) as error:
            self.update(1, VisitUpdate(expected_version=1, patient_id=99), self.background, self.db, self.clinician)
        self.assertEqual(error.exception.status_code, 422)

    def test_stale_revision_cannot_overwrite_saved_visit(self):
        self.update(1, VisitUpdate(expected_version=1, notes="first edit"), self.background, self.db, self.clinician)
        with self.assertRaises(HTTPException) as error:
            self.update(1, VisitUpdate(expected_version=1, notes="stale edit"), self.background, self.db, self.clinician)
        self.assertEqual(error.exception.status_code, 409)
        self.db.expire_all()
        self.assertEqual(self.db.get(Encounter, 1).notes, "first edit")

    def test_draft_preserves_lab_selection_without_issuing_orders(self):
        selections = {"labs": [{"id": 4, "name": "CBC", "price": 100, "lis_code": "CBC"}], "packages": []}
        background = BackgroundTasks()
        self.update(1, VisitUpdate(expected_version=1, status="Ongoing", draft_orders=selections), background, self.db, self.clinician)
        self.db.expire_all()
        self.assertEqual(self.db.get(Encounter, 1).draft_orders, selections)
        self.assertEqual(self.db.query(LabResult).count(), 0)
        self.assertEqual(len(background.tasks), 0)

    def test_completed_visit_is_signed_and_protected(self):
        self.update(1, VisitUpdate(expected_version=1, status="Completed"), self.background, self.db, self.clinician)
        self.db.expire_all()
        visit = self.db.get(Encounter, 1)
        self.assertEqual(visit.signed_by_id, 2)
        self.assertIsNotNone(visit.signed_at)
        with self.assertRaises(HTTPException) as error:
            self.update(1, VisitUpdate(expected_version=2, notes="rewrite"), self.background, self.db, self.clinician)
        self.assertEqual(error.exception.status_code, 409)

    def test_amendment_preserves_completed_note(self):
        self.db.get(Encounter, 1).status = "Completed"
        self.db.commit()
        result = self.amend(1, AmendmentCreate(reason="Clarification", note="Follow-up discussed"), self.db, self.clinician)
        self.db.expire_all()
        self.assertEqual(result.author_id, 2)
        self.assertEqual(self.db.get(Encounter, 1).notes, "before")
        self.assertEqual(self.db.query(EncounterAmendment).one().note, "Follow-up discussed")

    def test_open_visit_cannot_be_amended(self):
        with self.assertRaises(HTTPException) as error:
            self.amend(1, AmendmentCreate(reason="Clarification", note="Follow-up discussed"), self.db, self.clinician)
        self.assertEqual(error.exception.status_code, 409)

    def test_prescription_cannot_be_added_to_completed_visit(self):
        self.db.get(Encounter, 1).status = "Completed"
        self.db.commit()
        with self.assertRaises(HTTPException) as error:
            self.create_prescription(
                PrescriptionCreate(patient_id=1, doctor_id=2, encounter_id=1, items=[]),
                self.background, self.db,
            )
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.db.query(Prescription).count(), 0)

    def test_new_completed_visit_records_assigned_signer(self):
        visit = self.create(
            VisitPayload(patient_id=3, doctor_id=2, status="Completed"),
            self.background, self.db, self.clinician,
        )
        self.assertEqual(visit.version, 1)
        self.assertEqual(visit.signed_by_id, 2)
        self.assertIsNotNone(visit.signed_at)

    def test_other_clinician_cannot_sign_new_visit(self):
        with self.assertRaises(HTTPException) as error:
            self.create(
                VisitPayload(patient_id=3, doctor_id=4, status="Completed"),
                self.background, self.db, self.clinician,
            )
        self.assertEqual(error.exception.status_code, 403)
        self.assertEqual(self.db.query(Encounter).count(), 1)

    def test_queue_failure_does_not_turn_saved_visit_into_error(self):
        self.db.add(Appointment(id=42, patient_id=3, doctor_id=2, status="Scheduled"))
        self.db.commit()

        def failed_queue(db):
            raise RuntimeError("queue unavailable")

        with patch.dict(self.create.__globals__, {"get_live_queue": failed_queue}):
            visit = self.create(
                VisitPayload(patient_id=3, doctor_id=2, appointment_id=42, status="Open"),
                self.background, self.db, self.clinician,
            )
        self.assertEqual(self.db.get(Encounter, visit.id).status, "Open")
        self.assertEqual(self.db.get(Appointment, 42).status, "Open")


if __name__ == "__main__":
    unittest.main()
