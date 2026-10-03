"""Isolated route/business and legacy-schema regressions; no live services.

Load route bodies without authentication imports so these tests can run in the
shared review interpreter. SQLAlchemy models, queries and commits are real.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import sys
import unittest
import uuid
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import quote, urlparse

os.environ["DATABASE_URL"] = "postgresql://test:test@127.0.0.1:1/emr_regression"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.database import Base
from app.core.lis_migrations import migrate_patient_identity_uniqueness
import app.models
from app.models.patient import Patient
from app.models.lis_connector import ExternalLabOrder, PatientExternalIdentity

ROOT = Path(__file__).resolve().parents[3]


def load_bodies(path, names, namespace):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    nodes = [n for n in tree.body if getattr(n, "name", None) in names]
    for node in nodes:
        if isinstance(node, ast.FunctionDef):
            node.decorator_list = []
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add(Patient(id=1, first_name="Test", last_name="Patient", opd_number="OPD-7"))
        self.db.commit()
        self.config = {"host": "https://lis.example/clinic-a/api", "api_key": "lis_test"}
        self.clinic = "CLINIC-A"
        self.remote = {}
        self.posts = 0
        self.lose_response = False
        catalog_ns = runpy.run_path(str(ROOT / "Beta LIS/backend/services/catalog.py"))
        catalog_ns["Depends"] = Depends
        catalog_ns["get_current_user_or_integration_key"] = lambda: None
        load_bodies(ROOT / "Beta LIS/backend/routers/integrations.py", {"get_integration_catalog"}, catalog_ns)
        self.catalog_fn = catalog_ns["get_integration_catalog"]
        ns = dict(globals(), User=object, get_db=lambda: None, get_current_user=lambda: None)
        load_bodies(ROOT / "EMR/backend/app/api/lis_integration.py", {
            "LISOrderRequest", "_normalize_host", "_extract_lis_host", "_connection_identity",
            "_compute_payload_hash", "_get_or_create_lis_patient", "create_lis_order",
        }, ns)
        ns["_load_config"] = lambda db: self.config.copy()
        ns["_request"] = self.request
        self.ns = ns

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def request(self, config, method, path, **kwargs):
        if path == "/integrations/catalog":
            return self.catalog_fn(SimpleNamespace(clinic_id=self.clinic))
        remote_patient = config["host"] + ":" + self.clinic
        if path.startswith("/integrations/patients/by-reference/"):
            return {"id": remote_patient}
        if path.startswith("/integrations/orders/by-accession/"):
            key = (config["host"], self.clinic, path.rsplit("/", 1)[1])
            if key not in self.remote:
                raise HTTPException(404, "Not found")
            return self.remote[key]
        if method == "POST" and path == "/orders":
            self.posts += 1
            body = kwargs["json"]
            order = {**body, "id": f"ORDER-{self.posts}", "accessionNumber": body["customAccessionNumber"], "total": 300}
            self.remote[(config["host"], self.clinic, order["accessionNumber"])] = order
            if self.lose_response:
                self.lose_response = False
                raise HTTPException(504, "Response lost after acceptance")
            return order
        raise AssertionError((method, path))

    def submit(self, source="visit-1", tests=None, packages=None):
        payload = self.ns["LISOrderRequest"](patient_id=1, test_codes=tests or ["GLU"], package_codes=packages, source_id=source)
        return self.ns["create_lis_order"](payload, self.db, SimpleNamespace(username="doctor"))

    def test_actual_lis_combo_contract(self):
        catalog = self.catalog_fn(SimpleNamespace(clinic_id=self.clinic))
        combo = catalog["combos"][0]
        result = self.submit(tests=combo["testCodes"], packages=[combo["code"]])
        self.assertEqual(result["packageCodes"], [combo["code"]])
        self.assertEqual(self.posts, 1)

    def test_host_path_and_clinic_switch_are_isolated(self):
        first = self.submit()
        self.config["host"] = "https://other.example/api"
        second = self.submit()
        self.config["host"] = "https://lis.example/clinic-b/api"
        third = self.submit()
        self.clinic = "CLINIC-B"
        fourth = self.submit()
        self.assertEqual(len({r["accessionNumber"] for r in [first, second, third, fourth]}), 4)
        self.assertEqual(self.posts, 4)
        self.assertEqual(self.db.query(PatientExternalIdentity).count(), 4)

    def test_key_rotation_preserves_clinic_identity(self):
        first = self.submit()
        self.config["api_key"] = "lis_rotated"
        retry = self.submit()
        self.assertEqual(first["id"], retry["id"])
        self.assertTrue(retry["isExisting"])
        self.assertEqual(self.posts, 1)

    def test_lost_response_reconciles_without_second_post(self):
        self.lose_response = True
        with self.assertRaises(HTTPException):
            self.submit()
        result = self.submit()
        self.assertTrue(result["isExisting"])
        self.assertEqual(self.posts, 1)
        self.assertEqual(self.db.query(ExternalLabOrder).one().status, "ACCEPTED")

    def test_changed_tests_conflict_and_distinct_request_repeats(self):
        self.submit()
        with self.assertRaises(HTTPException) as caught:
            self.submit(tests=["CBC"])
        self.assertEqual(caught.exception.status_code, 409)
        self.submit(source="visit-2")
        self.assertEqual(self.posts, 2)

    def test_legacy_order_requires_remote_confirmation(self):
        self.db.add(ExternalLabOrder(uuid="legacy", patient_id=1, lis_host="lis.example", source_id="visit-1", accession_number="EMR-1-VISIT-1", test_codes=["GLU"], package_codes=[], status="ACCEPTED", remote_order_id="OLD"))
        self.db.commit()
        remote = {"id": "OLD", "patientId": self.config["host"] + ":" + self.clinic, "testCodes": ["GLU"], "packageCodes": [], "accessionNumber": "EMR-1-VISIT-1"}
        self.remote[(self.config["host"], self.clinic, "EMR-1-VISIT-1")] = remote
        result = self.submit()
        self.assertEqual(result["id"], "OLD")
        self.assertEqual(self.posts, 0)
        self.assertEqual(self.submit()["id"], "OLD")

    def test_remote_accession_for_another_patient_is_rejected(self):
        self.lose_response = True
        with self.assertRaises(HTTPException):
            self.submit()
        next(iter(self.remote.values()))["patientId"] = "OTHER-PATIENT"
        with self.assertRaises(HTTPException) as caught:
            self.submit()
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(self.posts, 1)


class MigrationTests(unittest.TestCase):
    def test_startup_propagates_upgrade_failure(self):
        namespace = {}
        load_bodies(ROOT / "EMR/backend/app/main.py", {"on_startup"}, namespace)
        seed = SimpleNamespace(seed_db=lambda: (_ for _ in ()).throw(RuntimeError("Upgrade failed")))
        with patch.dict(sys.modules, {"seed": seed}):
            with self.assertRaisesRegex(RuntimeError, "Upgrade failed"):
                namespace["on_startup"]()

    def test_upgrade_removes_legacy_unique_index(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE patient_external_identities (id INTEGER PRIMARY KEY, patient_id INTEGER NOT NULL, lis_host VARCHAR(128))"))
            conn.execute(text("CREATE UNIQUE INDEX ix_patient_external_identities_patient_id ON patient_external_identities(patient_id)"))
            conn.execute(text("CREATE INDEX ix_identity_host ON patient_external_identities(lis_host)"))
            migrate_patient_identity_uniqueness(conn)
            conn.execute(text("INSERT INTO patient_external_identities VALUES (1,7,'old'),(2,7,'new')"))
            self.assertIn("ix_identity_host", {i["name"] for i in inspect(conn).get_indexes("patient_external_identities")})
        engine.dispose()

    def test_upgrade_preserves_rows_and_replaces_global_uniqueness(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE patient_external_identities (id INTEGER PRIMARY KEY, patient_id INTEGER NOT NULL UNIQUE, lis_host VARCHAR(128), remote_patient_id VARCHAR(64))"))
            conn.execute(text("INSERT INTO patient_external_identities VALUES (1,7,'old','REMOTE-1')"))
        namespace = dict(engine=engine, inspect=inspect, text=text,
                         migrate_patient_identity_uniqueness=migrate_patient_identity_uniqueness)
        load_bodies(ROOT / "EMR/backend/seed.py", {"run_emr_auto_migrations"}, namespace)
        namespace["run_emr_auto_migrations"]()
        namespace["run_emr_auto_migrations"]()
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO patient_external_identities VALUES (2,7,'new','REMOTE-2')"))
            migrate_patient_identity_uniqueness(conn)
            self.assertEqual(conn.execute(text("SELECT remote_patient_id FROM patient_external_identities ORDER BY id")).scalars().all(), ["REMOTE-1", "REMOTE-2"])
            with self.assertRaises(IntegrityError):
                conn.execute(text("INSERT INTO patient_external_identities VALUES (3,7,'new','REMOTE-3')"))
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
