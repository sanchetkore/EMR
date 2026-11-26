"""Real HTTP authorization regressions using an isolated database."""
from test_security_remediation import SecurityTests
from app.api import prescriptions
from app.api.deps import get_current_user
from app.models.user import Role, User, Permission
from app.models.prescription import Prescription
from unittest.mock import patch
from pathlib import Path
import tempfile


class AuditBoundaryTests(SecurityTests):
    def setUp(self):
        super().setUp()
        self.app.include_router(prescriptions.router, prefix='/api/prescriptions')
        permission = Permission(name='manage_clinical')
        doctor_role = Role(name='Doctor', permissions=[permission])
        staff_role = Role(name='Nurse', permissions=[permission])
        self.doctor = User(username='doctor', email='doc@example.test', role=doctor_role, is_active=True)
        self.staff = User(username='nurse', email='nurse@example.test', role=staff_role, is_active=True)
        self.db.add_all([self.doctor, self.staff])
        self.db.commit()

    def identity(self, user):
        self.app.dependency_overrides[get_current_user] = lambda: user

    def test_forged_attribution_and_non_doctors_denied_without_writes(self):
        for actor, doctor_id in [(self.doctor, self.staff.id), (self.staff, self.doctor.id), (self.user, self.doctor.id)]:
            self.identity(actor)
            response = self.client.post('/api/prescriptions/', json={'patient_id': 1, 'doctor_id': doctor_id, 'items': []})
            self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(self.db.query(Prescription).count(), 0)

    def test_doctor_can_create_own_prescription(self):
        self.identity(self.doctor)
        with patch.object(prescriptions, 'get_live_queue', return_value={}), patch('app.services.whatsapp_service.send_prescription_whatsapp'), patch('app.services.sms_service.send_prescription_sms'):
            response = self.client.post('/api/prescriptions/', json={'patient_id': 1, 'doctor_id': self.doctor.id, 'items': []})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['doctor_id'], self.doctor.id)
        self.assertEqual(self.db.query(Prescription).count(), 1)

    def test_signature_owner_and_user_manager_only(self):
        with tempfile.TemporaryDirectory() as directory:
            signature = Path(directory) / 'signature.png'
            signature.write_bytes(b'synthetic-signature')
            self.doctor.signature_path = str(signature)
            self.db.commit()
            self.identity(self.staff)
            self.assertEqual(self.client.get(f'/api/users/{self.doctor.id}/signature/image').status_code, 403)
            self.assertEqual(self.client.get('/api/users/99999/signature/image').status_code, 403)
            for actor in [self.doctor, self.user]:
                self.identity(actor)
                response = self.client.get(f'/api/users/{self.doctor.id}/signature/image')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.content, b'synthetic-signature')

    def test_static_files_refuse_external_symlink(self):
        from fastapi.staticfiles import StaticFiles
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            public = root / 'public'
            public.mkdir()
            secret = root / 'private.txt'
            secret.write_text('private')
            try:
                (public / 'escape.txt').symlink_to(secret)
            except OSError as exc:
                self.skipTest(str(exc))
            app = FastAPI()
            app.mount('/assets', StaticFiles(directory=public, follow_symlink=False))
            with TestClient(app) as client:
                self.assertEqual(client.get('/assets/escape.txt').status_code, 404)
