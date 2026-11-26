"""HTTP security regressions with a private in-memory DB; no startup or external APIs."""
import os
import sys
import unittest
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch
import asyncio

os.environ['DATABASE_URL'] = 'postgresql://test:test@127.0.0.1:1/security_test'
os.environ['SECRET_KEY'] = 'isolated-security-test-key-not-for-production'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import app.models
from app.core.database import Base, get_db
from app.core.security import get_password_hash, create_access_token
from app.core.limiter import limiter
from app.core.request_limits import RequestBodyLimitMiddleware
from app.api import auth, clinic, users, media
from app.api.deps import get_current_user, get_current_user_ws
from app.models.user import User, Role, AuthSession
from app.models.clinic import ClinicProfile


class SecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password_hash = get_password_hash('demo-test-password')

    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.sessions()
        role = Role(name='Admin')
        self.user = User(username='demo', email='demo@example.test', hashed_password=self.password_hash, role=role, is_active=True)
        self.db.add_all([self.user, ClinicProfile(id=1, name='Demo', notification_settings={'messaging_api_key': 'SYNTHETIC-SECRET'})])
        self.db.commit()
        self.app = FastAPI()
        self.app.include_router(auth.router, prefix='/api/auth')
        self.app.include_router(clinic.router, prefix='/api/clinic')
        self.app.include_router(users.router, prefix='/api/users')
        def database():
            with self.sessions() as db:
                yield db
        self.app.dependency_overrides[get_db] = database
        @self.app.get('/private')
        def private(user=Depends(get_current_user)):
            return {'username': user.username}
        self.rate_patch = patch.object(limiter, 'enabled', False)
        self.rate_patch.start()
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.rate_patch.stop()
        self.db.close()
        self.engine.dispose()

    def login(self):
        response = self.client.post('/api/auth/login', data={'username': 'demo', 'password': 'demo-test-password'})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def headers(self, pair):
        return {'Authorization': 'Bearer ' + pair['access_token']}

    def test_demo_login_and_token_purposes(self):
        pair = self.login()
        self.assertEqual(self.client.get('/private', headers=self.headers(pair)).status_code, 200)
        self.assertEqual(self.client.get('/private', headers={'Authorization': 'Bearer ' + pair['refresh_token']}).status_code, 401)
        self.assertEqual(self.client.post('/api/auth/refresh', json={'refresh_token': pair['access_token']}).status_code, 401)
        old = create_access_token({'sub': 'demo'})
        self.assertEqual(self.client.get('/private', headers={'Authorization': 'Bearer ' + old}).status_code, 401)

    def test_rotation_replay_revokes_session_and_keeps_absolute_expiry(self):
        pair = self.login()
        expiry = self.db.query(AuthSession).one().expires_at
        refreshed = self.client.post('/api/auth/refresh', json={'refresh_token': pair['refresh_token']})
        self.assertEqual(refreshed.status_code, 200, refreshed.text)
        newer = refreshed.json()
        self.assertNotEqual(pair['refresh_token'], newer['refresh_token'])
        self.assertEqual(self.client.get('/private', headers=self.headers(newer)).status_code, 200)
        self.db.expire_all()
        self.assertEqual(self.db.query(AuthSession).one().expires_at, expiry)
        self.assertEqual(self.client.post('/api/auth/refresh', json={'refresh_token': pair['refresh_token']}).status_code, 401)
        self.assertEqual(self.client.get('/private', headers=self.headers(newer)).status_code, 401)
        self.assertEqual(self.client.post('/api/auth/refresh', json={'refresh_token': newer['refresh_token']}).status_code, 401)

    def test_disabled_user_and_reenable_do_not_restore_session(self):
        pair = self.login()
        response = self.client.delete(f'/api/users/{self.user.id}', headers=self.headers(pair))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.post('/api/auth/login', data={'username': 'demo', 'password': 'demo-test-password'}).status_code, 401)
        self.assertEqual(self.client.get('/private', headers=self.headers(pair)).status_code, 401)
        self.db.expire_all()
        self.user.is_active = True
        self.db.commit()
        self.assertEqual(self.client.get('/private', headers=self.headers(pair)).status_code, 401)
        self.login()

    def test_password_change_invalidates_existing_credentials(self):
        pair = self.login()
        self.user.hashed_password = get_password_hash('changed-test-password')
        self.db.commit()
        self.assertEqual(self.client.get('/private', headers=self.headers(pair)).status_code, 401)
        self.assertEqual(self.client.post('/api/auth/refresh', json={'refresh_token': pair['refresh_token']}).status_code, 401)

    def test_expired_session_rejected(self):
        pair = self.login()
        self.db.query(AuthSession).update({AuthSession.expires_at: datetime.utcnow() - timedelta(seconds=1)})
        self.db.commit()
        self.assertEqual(self.client.get('/private', headers=self.headers(pair)).status_code, 401)

    def test_public_profile_never_serializes_key_and_update_preserves_it(self):
        response = self.client.get('/api/clinic/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('SYNTHETIC-SECRET', response.text)
        self.assertNotIn('messaging_api_key', response.json()['notification_settings'])
        self.assertTrue(response.json()['is_messaging_authenticated'])
        response = self.client.put('/api/clinic/', headers=self.headers(self.login()), json={'name': 'Changed', 'notification_settings': {'messaging_api_key': 'INJECTED'}})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn('SYNTHETIC-SECRET', response.text)
        self.db.expire_all()
        self.assertEqual(self.db.query(ClinicProfile).one().notification_settings['messaging_api_key'], 'SYNTHETIC-SECRET')

    def test_websocket_auth_revalidates_disabled_users(self):
        pair = self.login()
        with patch('app.core.database.SessionLocal', self.sessions):
            self.assertIsNotNone(asyncio.run(get_current_user_ws(pair['access_token'])))
            self.assertIsNone(asyncio.run(get_current_user_ws(pair['refresh_token'])))
            self.user.is_active = False
            self.db.commit()
            self.assertIsNone(asyncio.run(get_current_user_ws(pair['access_token'])))

    def test_body_limit_before_form_parsing(self):
        self.app.add_middleware(RequestBodyLimitMiddleware, max_bytes=128)
        response = self.client.post('/api/auth/login', content=b'x' * 129, headers={'Content-Type': 'multipart/form-data; boundary=x'})
        self.assertEqual(response.status_code, 413)
        self.assertEqual(self.client.post('/api/auth/login', data={'username': 'demo', 'password': 'demo-test-password'}).status_code, 200)

    def test_media_rejects_sibling_directory_and_wrong_token_purpose(self):
        self.app.include_router(media.router, prefix='/api/media')
        token = media.create_media_token('../temp_pdfs-other/private.pdf')
        self.assertEqual(self.client.get('/api/media/' + token).status_code, 403)
        access = self.login()['access_token']
        self.assertEqual(self.client.get('/api/media/' + access).status_code, 400)

    def test_logo_rejects_active_content_and_oversize_images(self):
        headers = self.headers(self.login())
        response = self.client.post('/api/clinic/logo', headers=headers, files={'file': ('logo.html', b'<script>bad()</script>', 'text/html')})
        self.assertEqual(response.status_code, 400)
        response = self.client.post('/api/clinic/logo', headers=headers, files={'file': ('logo.png', b'not-a-png', 'image/png')})
        self.assertEqual(response.status_code, 400)
        response = self.client.post('/api/clinic/logo', headers=headers, files={'file': ('logo.png', b'x' * (5 * 1024 * 1024 + 1), 'image/png')})
        self.assertEqual(response.status_code, 413)


if __name__ == '__main__':
    unittest.main()
