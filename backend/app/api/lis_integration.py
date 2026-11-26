import base64
import hashlib
import json
import re
import uuid
from datetime import datetime, date
from typing import Annotated
from urllib.parse import urlparse, quote

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, TypeAdapter, ValidationError
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.api.deps import RequirePermission, get_current_user
from app.core.database import get_db
from app.core.security import SECRET_KEY
from app.models.lis_connector import LISConnector, PatientExternalIdentity, ExternalLabOrder
from app.models.patient import Patient
from app.models.user import User

router = APIRouter()
CONNECTOR_ID = 1


class LISConnectRequest(BaseModel):
    host: str = Field(min_length=8, max_length=500)
    api_key: str = Field(min_length=16, max_length=256)


class LISOrderRequest(BaseModel):
    patient_id: int
    test_codes: list[str] = Field(min_length=1)
    package_codes: list[str] | None = None
    source_id: str = Field(min_length=1, max_length=64)
    notes: str | None = Field(default=None, max_length=1000)


class LISReportResult(BaseModel):
    testName: str
    value: str | float | None = None
    unit: str | None = None
    referenceRange: str | None = None
    flag: str | None = None
    reviewerComment: str | None = None


class LISPatientReport(BaseModel):
    id: str
    accessionNumber: str
    version: int
    releasedAt: datetime
    resultsSnapshot: list[LISReportResult]


class LISReportEnvelope(LISPatientReport):
    patientId: str
    status: str
    isLatest: bool


def _extract_lis_host(host_url: str) -> str:
    parsed = urlparse(host_url if "://" in host_url else f"https://{host_url}")
    return parsed.netloc or host_url


def _compute_payload_hash(patient_id: int, test_codes: list[str], package_codes: list[str] | None) -> str:
    sorted_tests = sorted(test_codes or [])
    sorted_packages = sorted(package_codes or [])
    canonical = json.dumps({
        "patient_id": patient_id,
        "tests": sorted_tests,
        "packages": sorted_packages
    }, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _connection_identity(config: dict, catalog: dict) -> str:
    host = _normalize_host(config["host"])
    clinic = catalog.get("clinicId")
    # Key rotation retains identity when LIS provides authenticated clinic scope.
    scope = str(clinic) if clinic else hashlib.sha256(
        (config.get("api_key") or config.get("token") or "").encode()
    ).hexdigest()
    return hashlib.sha256(json.dumps([host, scope]).encode()).hexdigest()


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY.encode()).digest())
    return Fernet(key)


def _load_config(db: Session) -> dict | None:
    row = db.get(LISConnector, CONNECTOR_ID)
    if not row:
        return None
    try:
        return json.loads(_fernet().decrypt(row.encrypted_config.encode()).decode())
    except (InvalidToken, ValueError, TypeError):
        raise HTTPException(status_code=500, detail="Saved LIS connection cannot be decrypted. Reconnect the LIS.")


def _normalize_host(host: str) -> str:
    host = host.strip().rstrip("/")
    parsed = urlparse(host if "://" in host else f"https://{host}")
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise HTTPException(status_code=422, detail="Enter a valid LIS host URL.")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise HTTPException(status_code=422, detail="Use HTTPS for the LIS connection.")
    path = parsed.path.rstrip("/")
    if path.endswith("/api"):
        return f"{parsed.scheme}://{parsed.netloc}{path}"
    return f"{parsed.scheme}://{parsed.netloc}{path}/api"


def _probe_health(config: dict) -> tuple[str, str | None]:
    credential = config.get("api_key") or config.get("token")
    if not credential:
        return "NOT_CONFIGURED", "No credentials saved."
    try:
        res = httpx.get(
            f"{config['host']}/integrations/catalog",
            headers={"Authorization": f"Bearer {credential}"},
            timeout=4.0
        )
        if res.status_code in {401, 403}:
            return "KEY_REJECTED", "LIS API key was rejected or revoked."
        if res.is_success:
            try:
                data = res.json()
                if isinstance(data, dict) and "tests" in data and isinstance(data["tests"], list):
                    return "CONNECTED", None
                return "INCOMPATIBLE", "LIS catalog format is incompatible."
            except Exception:
                return "INCOMPATIBLE", "LIS returned a non-JSON response."
        return "TEMPORARILY_UNAVAILABLE", f"LIS returned HTTP {res.status_code}"
    except httpx.TimeoutException:
        return "TEMPORARILY_UNAVAILABLE", "Connection timed out reaching LIS."
    except httpx.HTTPError as e:
        return "TEMPORARILY_UNAVAILABLE", f"Could not reach LIS: {str(e)}"


def _request(config: dict, method: str, path: str, **kwargs):
    credential = config.get("api_key") or config.get("token")
    if not credential:
        raise HTTPException(status_code=409, detail="LIS connection needs to be reconnected.")
    url = f"{config['host']}{path}"
    try:
        response = httpx.request(method, url, headers={"Authorization": f"Bearer {credential}"}, timeout=15, **kwargs)
        # Compatibility for connections saved before persistent API keys were added.
        if response.status_code == 401 and not config.get("api_key") and config.get("identifier") and config.get("password"):
            login = httpx.post(
                f"{config['host']}/auth/staff-login",
                json={"identifier": config["identifier"], "password": config["password"]},
                timeout=15,
            )
            if not login.is_success:
                raise HTTPException(status_code=409, detail="LIS credentials expired or were changed. Reconnect the LIS.")
            config["token"] = login.json().get("token")
            response = httpx.request(method, url, headers={"Authorization": f"Bearer {config['token']}"}, timeout=15, **kwargs)
        response.raise_for_status()
        try:
            return response.json()
        except ValueError:
            raise HTTPException(status_code=502, detail="LIS server returned a non-JSON response.")
    except HTTPException:
        raise
    except httpx.HTTPStatusError as error:
        detail = "The LIS rejected this request. Check the LIS account permissions and selected tests."
        try:
            detail = error.response.json().get("detail", detail)
        except (ValueError, AttributeError):
            pass
        raise HTTPException(status_code=error.response.status_code, detail=detail)
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Could not reach the LIS. Check the host and network connection.")


def _persist_config(db: Session, config: dict, mode: str = "CONNECTED", health: str = "CONNECTED"):
    encrypted = _fernet().encrypt(json.dumps(config).encode()).decode()
    row = db.get(LISConnector, CONNECTOR_ID)
    now = datetime.utcnow()
    if row:
        row.encrypted_config = encrypted
        row.configured_mode = mode
        row.last_health_status = health
        row.last_health_check = now
    else:
        db.add(LISConnector(
            id=CONNECTOR_ID,
            encrypted_config=encrypted,
            configured_mode=mode,
            last_health_status=health,
            last_health_check=now,
        ))
    db.commit()


@router.post("/connect", dependencies=[Depends(RequirePermission("manage_users"))])
def connect_lis(payload: LISConnectRequest, db: Session = Depends(get_db)):
    host = _normalize_host(payload.host)
    api_key = payload.api_key.strip()

    # Reject JWT passed as API key
    if api_key.startswith("ey") or api_key.count(".") == 2:
        raise HTTPException(
            status_code=422,
            detail="You entered a JWT user session token instead of an integration key. Create a long-lived key starting with 'lis_' in LIS Settings."
        )
    if not api_key.startswith("lis_"):
        raise HTTPException(
            status_code=422,
            detail="Invalid key format. LIS integration API keys must begin with 'lis_'."
        )

    config = {"host": host, "api_key": api_key}
    health_status, err = _probe_health(config)
    if health_status == "KEY_REJECTED":
        raise HTTPException(status_code=401, detail="LIS API key was rejected. Verify permissions or rotate key in LIS Settings.")
    if health_status == "INCOMPATIBLE":
        raise HTTPException(status_code=502, detail=f"LIS API is incompatible: {err or 'Unknown format'}")
    if health_status == "TEMPORARILY_UNAVAILABLE":
        raise HTTPException(status_code=502, detail=f"Could not reach LIS host: {err or 'Network error'}")

    catalog = _request(config, "GET", "/integrations/catalog")
    config["connection_id"] = _connection_identity(config, catalog)
    _persist_config(db, config, mode="CONNECTED", health="CONNECTED")
    return {"connected": True, "host": host, "status": "CONNECTED", "account": "LIS API key"}


@router.get("/status")
def lis_status(check_health: bool = False, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    connector = db.get(LISConnector, CONNECTOR_ID)
    if not connector or connector.configured_mode == "DISCONNECTED":
        return {"configured": False, "connected": False, "status": "NOT_CONFIGURED", "host": None}

    config = _load_config(db)
    if not config:
        return {"configured": False, "connected": False, "status": "NOT_CONFIGURED", "host": None}

    # Upgrade saved connections before the UI creates durable submission keys.
    if not config.get("connection_id"):
        try:
            catalog = _request(config, "GET", "/integrations/catalog")
            config["connection_id"] = _connection_identity(config, catalog)
            _persist_config(db, config, mode="CONNECTED", health="CONNECTED")
        except HTTPException as error:
            connector.last_health_status = "KEY_REJECTED" if error.status_code in {401, 403} else "TEMPORARILY_UNAVAILABLE"
            connector.last_health_check = datetime.utcnow()
            db.commit()

    health_status = connector.last_health_status or "UNKNOWN"
    if check_health or health_status == "UNKNOWN":
        new_status, _ = _probe_health(config)
        connector.last_health_status = new_status
        connector.last_health_check = datetime.utcnow()
        db.commit()
        health_status = new_status

    return {
        "configured": True,
        "connected": health_status == "CONNECTED",
        "status": health_status,
        "host": config.get("host"),
        "connection_id": config.get("connection_id"),
        "last_checked": connector.last_health_check.isoformat() if connector.last_health_check else None,
        "account": "LIS API key" if config.get("api_key") else "Staff account"
    }


@router.delete("/disconnect", dependencies=[Depends(RequirePermission("manage_users"))])
def disconnect_lis(db: Session = Depends(get_db)):
    row = db.get(LISConnector, CONNECTOR_ID)
    if row:
        row.configured_mode = "DISCONNECTED"
        row.last_health_status = "NOT_CONFIGURED"
        db.delete(row)
        db.commit()
    return {"connected": False, "status": "NOT_CONFIGURED"}


@router.get("/patients/{patient_id}/reports", response_model=list[LISPatientReport])
def get_patient_reports(
    patient_id: int,
    response: Response,
    db: Session = Depends(get_db),
    _user=Depends(RequirePermission("view_clinical")),
    accession_number: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
):
    response.headers["Cache-Control"] = "no-store"
    if not db.get(Patient, patient_id):
        raise HTTPException(status_code=404, detail="Patient not found.")
    return fetch_released_patient_reports(db, patient_id, accession_number)


def fetch_released_patient_reports(
    db: Session, patient_id: int, accession_number: str | None = None,
    *, report_params: dict | None = None,
) -> list[LISPatientReport]:
    config = _load_config(db)
    if not config:
        return []
    if not config.get("api_key"):
        raise HTTPException(status_code=409, detail="Reconnect LIS with a clinic integration key to read reports.")

    connection_id = config.get("connection_id")
    if not connection_id:
        try:
            connection_id = _connection_identity(config, _request(config, "GET", "/integrations/catalog"))
        except HTTPException as error:
            raise HTTPException(status_code=502, detail="Could not verify the LIS connection.") from error

    identities = db.query(PatientExternalIdentity).filter(PatientExternalIdentity.lis_host == connection_id)
    identity = identities.filter(PatientExternalIdentity.patient_id == patient_id).one_or_none()
    if not identity:
        return []
    remote_id = identity.remote_patient_id
    if identities.filter(
        PatientExternalIdentity.remote_patient_id == remote_id,
        PatientExternalIdentity.patient_id != patient_id,
    ).first():
        raise HTTPException(status_code=409, detail="This LIS patient link must be reconciled before reports can be shown.")
    try:
        params = dict(report_params or {})
        if accession_number is not None:
            params["accession_number"] = accession_number
        payload = _request(config, "GET", f"/integrations/patients/{quote(remote_id, safe='')}/reports",
                           **({"params": params} if params else {}))
        reports = TypeAdapter(list[LISReportEnvelope]).validate_python(payload)
    except (HTTPException, ValidationError) as error:
        raise HTTPException(status_code=502, detail="Could not load released reports from LIS.") from error
    if any(report.patientId != remote_id or report.status != "Released" or not report.isLatest for report in reports):
        raise HTTPException(status_code=502, detail="LIS returned reports that do not match the patient link.")
    if accession_number is not None:
        return [report for report in reports if report.accessionNumber == accession_number]
    return reports


@router.get("/catalog")
def get_lis_catalog(db: Session = Depends(get_db), _user=Depends(RequirePermission("view_clinical"))):
    config = _load_config(db)
    if not config:
        raise HTTPException(status_code=409, detail="Connect an LIS to load its catalog.")
    result = _request(config, "GET", "/integrations/catalog")
    row = db.get(LISConnector, CONNECTOR_ID)
    if row:
        row.last_catalog_refresh = datetime.utcnow()
        row.last_health_status = "CONNECTED"
        db.commit()
    return result


def _get_or_create_lis_patient(db: Session, config: dict, patient: Patient, referring_doctor: str) -> str:
    lis_host = config["connection_id"]

    def _persist_identity(remote_id: str, opd: str | None) -> str:
        row = db.query(PatientExternalIdentity).filter(
            PatientExternalIdentity.patient_id == patient.id,
            PatientExternalIdentity.lis_host == lis_host
        ).first()
        if row:
            row.remote_patient_id = remote_id
            row.opd_number = opd
            row.verified_at = datetime.utcnow()
        else:
            db.add(PatientExternalIdentity(
                patient_id=patient.id,
                lis_host=lis_host,
                remote_patient_id=remote_id,
                opd_number=opd,
            ))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            row = db.query(PatientExternalIdentity).filter(
                PatientExternalIdentity.patient_id == patient.id,
                PatientExternalIdentity.lis_host == lis_host
            ).first()
            if row:
                row.remote_patient_id = remote_id
                db.commit()
            else:
                raise HTTPException(status_code=409, detail="Could not persist the LIS patient mapping. Resolve the database identity conflict before retrying.")
        return remote_id

    # 1. Durable database identity lookup scoped by lis_host
    identity = db.query(PatientExternalIdentity).filter(
        PatientExternalIdentity.patient_id == patient.id,
        PatientExternalIdentity.lis_host == lis_host
    ).first()
    if identity:
        return identity.remote_patient_id

    opd_number = (patient.opd_number or "").strip()
    mrn = f"EMR-{patient.id}"

    # 2. Reference lookup in LIS
    try:
        reference = f"OPD-{opd_number}" if opd_number else mrn
        match = _request(config, "GET", f"/integrations/patients/by-reference/{quote(reference, safe='')}")
        if match.get("id"):
            return _persist_identity(match["id"], opd_number or None)
    except HTTPException as error:
        if error.status_code != 404:
            raise

    # 3. Match by OPD and demographics
    try:
        match = _request(config, "POST", "/integrations/patients/match", json={
            "firstName": patient.first_name,
            "lastName": patient.last_name,
            "dob": patient.dob.isoformat() if patient.dob else None,
            "mobile": patient.contact_number,
            "email": patient.email,
            "opdNumber": opd_number or None,
        })
        if match.get("id"):
            return _persist_identity(match["id"], opd_number or None)
    except HTTPException as error:
        if error.status_code != 404:
            raise

    # 4. Create new patient in LIS
    today = date.today()
    dob = patient.dob.isoformat() if patient.dob else ""
    age = max(0, today.year - patient.dob.year - ((today.month, today.day) < (patient.dob.month, patient.dob.day))) if patient.dob else 0
    body = {
        "mrn": mrn,
        "opdNumber": opd_number or None,
        "firstName": patient.first_name,
        "lastName": patient.last_name,
        "age": age,
        "gender": patient.gender or "Unknown",
        "dob": dob,
        "mobile": patient.contact_number or "",
        "email": patient.email or f"patient-{patient.id}@no-email.invalid",
        "address": patient.address or "Not provided",
        "referringDoctor": referring_doctor or "EMR Clinic",
    }
    try:
        created = _request(config, "POST", "/patients", json=body)
        return _persist_identity(created["id"], opd_number or None)
    except HTTPException as error:
        if error.status_code == 409:
            # Re-run strict match in case another concurrent request created it
            try:
                retry_match = _request(config, "POST", "/integrations/patients/match", json={
                    "firstName": patient.first_name,
                    "lastName": patient.last_name,
                    "dob": patient.dob.isoformat() if patient.dob else None,
                    "mobile": patient.contact_number,
                    "email": patient.email,
                    "opdNumber": opd_number or None,
                })
                if retry_match.get("id"):
                    return _persist_identity(retry_match["id"], opd_number or None)
            except Exception:
                pass
            raise HTTPException(
                status_code=409,
                detail="A patient with matching details already exists in the LIS. Ask the laboratory to link the existing patient to this EMR record."
            )
        raise


@router.post("/orders", dependencies=[Depends(RequirePermission("manage_clinical"))])
def create_lis_order(payload: LISOrderRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user), expected_connection_id: str | None = None):
    config = _load_config(db)
    if not config:
        raise HTTPException(status_code=409, detail="Connect an LIS before placing a laboratory order.")
    patient = db.query(Patient).filter(Patient.id == payload.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")

    catalog = _request(config, "GET", "/integrations/catalog")
    valid_tests = {item["code"] for item in catalog.get("tests", [])}
    valid_packages = {pkg["code"] for pkg in catalog.get("combos", catalog.get("packages", []))}
    invalid_tests = sorted(set(payload.test_codes) - valid_tests)
    if invalid_tests:
        raise HTTPException(status_code=422, detail=f"These tests are not in the connected LIS catalog: {', '.join(invalid_tests)}")
    if payload.package_codes:
        invalid_packages = sorted(set(payload.package_codes) - valid_packages)
        if invalid_packages:
            raise HTTPException(status_code=422, detail=f"These packages are not in the connected LIS catalog: {', '.join(invalid_packages)}")

    config = {**config, "connection_id": _connection_identity(config, catalog)}
    if expected_connection_id and config["connection_id"] != expected_connection_id:
        raise HTTPException(status_code=409, detail="The LIS connection changed after this laboratory request was saved. Review and resolve this request before submitting it.")
    lis_host = config["connection_id"]
    lis_patient_id = _get_or_create_lis_patient(db, config, patient, current_user.username)

    # Scope accessions to deployment, authenticated clinic, patient and request.
    order_digest = hashlib.sha256(json.dumps([lis_host, patient.id, payload.source_id]).encode()).hexdigest()[:40]
    accession = f"EMR-{order_digest}".upper()

    req_payload_hash = _compute_payload_hash(patient.id, payload.test_codes, payload.package_codes)

    # Check local order ledger for durable idempotent handling
    ledger = db.query(ExternalLabOrder).filter(
        ExternalLabOrder.patient_id == patient.id,
        ExternalLabOrder.source_id == payload.source_id,
        ExternalLabOrder.lis_host == lis_host,
    ).first()
    if ledger:
        accession = ledger.accession_number
    if ledger and ledger.status == "ACCEPTED":
        ledger_tests = sorted(ledger.test_codes or [])
        req_tests = sorted(payload.test_codes or [])
        ledger_packages = sorted(ledger.package_codes or [])
        req_packages = sorted(payload.package_codes or [])
        if ledger.patient_id != patient.id or ledger_tests != req_tests or ledger_packages != req_packages:
            raise HTTPException(
                status_code=409,
                detail=f"An order with accession '{accession}' already exists with different tests or packages. Contact the laboratory."
            )
        return {
            "id": ledger.remote_order_id or ledger.uuid,
            "accessionNumber": ledger.accession_number,
            "patientId": lis_patient_id,
            "status": "Accepted",
            "testCodes": ledger.test_codes,
            "packageCodes": ledger.package_codes or [],
            "total": ledger.authoritative_price or 0.0,
            "isExisting": True,
        }

    # Legacy rows lack authenticated deployment/clinic scope. Trust them only
    # after the currently connected LIS confirms accession and patient ownership.
    legacy = None
    if not ledger:
        legacy = db.query(ExternalLabOrder).filter(
            ExternalLabOrder.patient_id == patient.id,
            ExternalLabOrder.source_id == payload.source_id,
            ExternalLabOrder.lis_host.in_(["", _extract_lis_host(config["host"])]),
        ).first()
    existing = None
    if legacy:
        try:
            existing = _request(config, "GET", f"/integrations/orders/by-accession/{quote(legacy.accession_number, safe='')}")
        except HTTPException as error:
            if error.status_code != 404:
                raise
        if existing:
            accession = legacy.accession_number
            ledger = legacy

    # Check remote LIS by accession
    try:
        if not existing:
            existing = _request(config, "GET", f"/integrations/orders/by-accession/{quote(accession, safe='')}")
    except HTTPException as error:
        if error.status_code != 404:
            raise
        existing = None

    if existing:
        if str(existing.get("patientId")) != str(lis_patient_id):
            raise HTTPException(status_code=409, detail="This accession belongs to a different LIS patient.")
        existing_tests = sorted(existing.get("testCodes") or [])
        req_tests = sorted(payload.test_codes or [])
        existing_packages = sorted(existing.get("packageCodes") or [])
        req_packages = sorted(payload.package_codes or [])
        if existing_tests != req_tests or existing_packages != req_packages:
            raise HTTPException(
                status_code=409,
                detail="This visit already has an accepted order in LIS with different tests or packages. Contact the laboratory."
            )
        if not ledger:
            ledger = ExternalLabOrder(
                uuid=f"ELO-{uuid.uuid4().hex[:12].upper()}",
                patient_id=patient.id,
                lis_host=lis_host,
                encounter_id=int(payload.source_id.split("-")[-1]) if payload.source_id.startswith("visit-") and payload.source_id.split("-")[-1].isdigit() else None,
                source_id=payload.source_id,
                accession_number=accession,
                test_codes=payload.test_codes,
                package_codes=payload.package_codes,
                payload_hash=req_payload_hash,
                status="ACCEPTED",
                remote_order_id=existing.get("id"),
                authoritative_price=existing.get("total", 0.0),
            )
            try:
                db.add(ledger)
                db.commit()
            except IntegrityError:
                db.rollback()
                ledger = db.query(ExternalLabOrder).filter(ExternalLabOrder.accession_number == accession).first()
        else:
            ledger.lis_host = lis_host
            ledger.status = "ACCEPTED"
            ledger.remote_order_id = existing.get("id")
            ledger.authoritative_price = existing.get("total", 0.0)
            ledger.payload_hash = req_payload_hash
            db.commit()

        return {
            "id": existing.get("id"),
            "accessionNumber": existing.get("accessionNumber", accession),
            "patientId": lis_patient_id,
            "status": existing.get("status", "Ordered"),
            "testCodes": existing.get("testCodes", payload.test_codes),
            "packageCodes": existing.get("packageCodes") or [],
            "total": existing.get("total", 0.0),
            "isExisting": True,
        }

    # Record pending submission in local ledger
    if not ledger:
        ledger = ExternalLabOrder(
            uuid=f"ELO-{uuid.uuid4().hex[:12].upper()}",
            patient_id=patient.id,
            lis_host=lis_host,
            encounter_id=int(payload.source_id.split("-")[-1]) if payload.source_id.startswith("visit-") and payload.source_id.split("-")[-1].isdigit() else None,
            source_id=payload.source_id,
            accession_number=accession,
            test_codes=payload.test_codes,
            package_codes=payload.package_codes,
            payload_hash=req_payload_hash,
            status="PENDING",
        )
        try:
            db.add(ledger)
            db.commit()
        except IntegrityError:
            db.rollback()
            ledger = db.query(ExternalLabOrder).filter(ExternalLabOrder.accession_number == accession).first()
    else:
        ledger.status = "PENDING"
        ledger.payload_hash = req_payload_hash
        ledger.test_codes = payload.test_codes
        ledger.package_codes = payload.package_codes
        db.commit()

    body = {
        "patientId": lis_patient_id,
        "testCodes": list(dict.fromkeys(payload.test_codes)),
        "packageCodes": list(dict.fromkeys(payload.package_codes)) if payload.package_codes else None,
        "priority": "ROUTINE",
        "paymentMethod": "Clinic Billing",
        "orderSource": "EMR Integration",
        "customerNotes": f"Ordered in EMR by {current_user.username}; source {payload.source_id}. {payload.notes or ''}".strip(),
        "customAccessionNumber": accession,
    }

    try:
        order = _request(config, "POST", "/orders", json=body)
        ledger.status = "ACCEPTED"
        ledger.remote_order_id = order.get("id")
        ledger.authoritative_price = order.get("total")
        db.commit()
        return {
            "id": order.get("id"),
            "accessionNumber": order.get("accessionNumber", accession),
            "patientId": lis_patient_id,
            "status": order.get("status", "Ordered"),
            "testCodes": order.get("testCodes", payload.test_codes),
            "packageCodes": order.get("packageCodes") or [],
            "total": order.get("total", 0.0),
            "isExisting": False,
        }
    except Exception as exc:
        ledger.status = "FAILED"
        ledger.error_message = str(exc)
        db.commit()
        raise
