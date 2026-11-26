from app.api.mobile.clock import clinic_now
from datetime import date, datetime
import json
import math
from typing import Annotated, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.models.patient import Patient
from app.services.clinic_closures import check_booking_day, closure_reason
from app.models.lab_result import LabResult, LabCatalog, ComboLabTest
from app.models.lis_connector import LISConnector
from app.models.user import User
from app.models.mobile import MobileBloodPickup, MobilePatientAlert, MobilePaymentRecord, MobilePickupCombo
from app.models.clinical import Invoice, InvoiceItem
from app.api.mobile.deps import get_current_patient
from app.api.lis_integration import CONNECTOR_ID, LISPatientReport, fetch_released_patient_reports, _load_config, _request
from app.services.lab_report_recency import completed_lab_results, report_recency
from app.services.pickup_slots import booked_windows, pickup_schedule, remaining_collections

router = APIRouter(prefix="/labs", tags=["mobile-labs"])

TestCode = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
TestSelection = Annotated[list[TestCode], Field(min_length=1, max_length=50)]


class BookPickupRequest(BaseModel):
    testPanelTitle: str = ""
    testCodes: Optional[str] = "LAB-PANEL"
    selectedTestCodes: TestSelection | None = None
    collectionName: str | None = Field(default=None, max_length=80)
    fastingRequired: bool = True
    pickupDateIso: str
    pickupDateLabel: Optional[str] = None
    timeWindow: str  # e.g. "07:30 AM – 08:30 AM"
    address: str
    notes: Optional[str] = Field(default="", max_length=2000)
    amountPaidCents: int = 0
    paymentMethodLabel: str = "Pay at collection"
    transactionId: Optional[str] = None

@router.get("/catalog")
def get_lab_catalog(db: Session = Depends(get_db)):
    connector = db.get(LISConnector, CONNECTOR_ID)
    if connector and connector.configured_mode != "DISCONNECTED":
        try:
            config = _load_config(db)
            payload = _request(config, "GET", "/integrations/catalog")
            tests = {item["code"]: catalog_entry(
                f"LIS:{item['code']}", item["name"], item.get("department") or "",
                item["price"], None, [f"LIS:{item['code']}"],
            ) for item in payload["tests"]}
            packages = [
                catalog_entry(f"LIS-PACKAGE:{item['code']}", item["name"], "Lab package",
                              item["price"], None, [tests[code]["codes"] for code in item["testCodes"]])
                for item in payload.get("packages", payload.get("combos", []))
                if item["testCodes"] and all(code in tests for code in item["testCodes"])
            ]
            return sorted([*tests.values(), *packages], key=lambda item: item["title"].casefold())
        except (HTTPException, KeyError, TypeError, ValueError, OverflowError) as error:
            raise HTTPException(503, "The connected LIS catalog is currently unavailable.") from error
    tests = {item.id: catalog_entry(str(item.id), item.name, item.description or "", item.price or 0, 24, [str(item.id)])
             for item in db.query(LabCatalog).filter(LabCatalog.is_active.is_(True))}
    packages = [
        catalog_entry(f"EMR-PACKAGE:{item.id}", item.name, "Lab package", item.price or 0, 24,
                      [tests[code]["codes"] for code in item.test_ids])
        for item in db.query(ComboLabTest).filter(ComboLabTest.is_active.is_(True))
        if item.test_ids and all(code in tests for code in item.test_ids)
    ]
    return sorted([*tests.values(), *packages], key=lambda item: item["title"].casefold())


def catalog_entry(code, name, description, price, turnaround, included_codes):
    amount = round(float(price) * 100)
    if amount < 0:
        raise ValueError("Catalog price cannot be negative")
    return {
        "id": code, "codes": code, "title": name, "description": description,
        "fastingRequired": False, "turnaroundHours": turnaround, "priceCents": amount,
        "includedCodes": list(dict.fromkeys(included_codes)),
    }


def resolve_pickup_tests(db, codes):
    if len(codes) != len(set(codes)):
        raise HTTPException(422, "Select each test only once.")
    catalog = {item["codes"]: item for item in get_lab_catalog(db)}
    if not codes or any(code not in catalog for code in codes):
        raise HTTPException(409, "One or more selected tests are no longer available.")
    items = [catalog[code] for code in codes]
    included = [code for item in items for code in item["includedCodes"]]
    if len(included) != len(set(included)):
        raise HTTPException(422, "The selected tests and packages contain the same test more than once.")
    return items


class ComboName(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class CreatePickupCombo(ComboName):
    testCodes: TestSelection


def combo_response(combo):
    return {"id": combo.id, "name": combo.name, "testCodes": combo.test_codes}


@router.get("/pickup-combos")
def get_pickup_combos(current_patient: Patient = Depends(get_current_patient), db: Session = Depends(get_db)):
    combos = db.query(MobilePickupCombo).filter_by(patient_id=current_patient.id).order_by(MobilePickupCombo.id.desc())
    return [combo_response(combo) for combo in combos]


@router.post("/pickup-combos", status_code=201)
def save_pickup_combo(payload: CreatePickupCombo, current_patient: Patient = Depends(get_current_patient),
                      db: Session = Depends(get_db)):
    resolve_pickup_tests(db, payload.testCodes)
    combo = MobilePickupCombo(patient_id=current_patient.id, name=payload.name, test_codes=payload.testCodes)
    db.add(combo)
    db.commit()
    db.refresh(combo)
    return combo_response(combo)


@router.patch("/pickup-combos/{combo_id}")
def rename_pickup_combo(combo_id: int, payload: ComboName, current_patient: Patient = Depends(get_current_patient),
                        db: Session = Depends(get_db)):
    combo = db.query(MobilePickupCombo).filter_by(id=combo_id, patient_id=current_patient.id).first()
    if combo is None:
        raise HTTPException(404, "Saved combo not found.")
    combo.name = payload.name
    db.commit()
    return combo_response(combo)


@router.get("/pickup-slots")
def get_pickup_slots(day: date, _patient: Patient = Depends(get_current_patient), db: Session = Depends(get_db)):
    if day <= clinic_now().date() or closure_reason(db, day):
        return []
    _, schedule = pickup_schedule(db)
    windows = booked_windows(db, day)
    return [{"label": slot.label, "remaining": remaining_collections(slot, windows)} for slot in schedule.slots]


@router.get("/pickups")
def get_my_pickups(
    current_patient: Patient = Depends(get_current_patient),
    db: Session = Depends(get_db)
):
    pickups = db.query(MobileBloodPickup).filter(
        MobileBloodPickup.patient_id == current_patient.id
    ).order_by(MobileBloodPickup.created_at.desc()).all()

    return [
        {
            "id": p.id,
            "testPanelTitle": p.test_panel_title,
            "testCodes": p.test_codes or "LAB-PANEL",
            "fastingRequired": p.fasting_required,
            "pickupDateIso": p.pickup_date_iso,
            "pickupDateLabel": p.pickup_date_label or p.pickup_date_iso,
            "timeWindow": p.time_window,
            "address": p.address,
            "notes": p.notes or "",
            "status": p.status,
            "paymentStatus": p.payment_status,
            "amountPaidCents": p.amount_paid_cents,
            "paymentMethodLabel": p.payment_method_label or "Pay at collection",
            "transactionId": p.transaction_id or "",
            "reminderEnabled": p.reminder_enabled,
            "createdAtMillis": int(p.created_at.timestamp() * 1000)
        }
        for p in pickups
    ]

@router.post("/pickups")
def book_blood_pickup(
    payload: BookPickupRequest,
    current_patient: Patient = Depends(get_current_patient),
    db: Session = Depends(get_db)
):
    try:
        collection_date = datetime.strptime(payload.pickupDateIso, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid collection date")
    if collection_date <= clinic_now().date():
        raise HTTPException(status_code=400, detail="Collection must be booked from tomorrow onwards")
    check_booking_day(db, collection_date)
    if len(payload.address.strip()) < 10 or len(payload.address) > 2000:
        raise HTTPException(status_code=400, detail="Enter a complete collection address")
    if payload.amountPaidCents or payload.transactionId:
        raise HTTPException(status_code=400, detail="Online payments are not enabled for bookings")
    codes = payload.selectedTestCodes or ([payload.testCodes] if payload.testCodes else [])
    items = resolve_pickup_tests(db, codes)
    stored_codes = codes[0] if len(codes) == 1 else json.dumps(sorted(codes), separators=(",", ":"))
    _, schedule = pickup_schedule(db, lock=True)
    slot = next((slot for slot in schedule.slots if slot.label == payload.timeWindow), None)
    if slot is None or not remaining_collections(slot, booked_windows(db, collection_date)):
        raise HTTPException(409, "This collection slot is no longer available. Choose another time.")
    duplicate = db.query(MobileBloodPickup).filter(
        MobileBloodPickup.patient_id == current_patient.id,
        MobileBloodPickup.pickup_date_iso == payload.pickupDateIso,
        MobileBloodPickup.test_codes == stored_codes,
        MobileBloodPickup.status == "SCHEDULED"
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="This test already has a scheduled collection on that date")
    title = (payload.collectionName or "").strip() or ", ".join(item["title"] for item in items)
    pickup = MobileBloodPickup(
        patient_id=current_patient.id,
        test_panel_title=title[:255],
        test_codes=stored_codes,
        fasting_required=any(item["fastingRequired"] for item in items),
        pickup_date_iso=payload.pickupDateIso,
        pickup_date_label=payload.pickupDateLabel or payload.pickupDateIso,
        time_window=payload.timeWindow,
        address=payload.address,
        notes=payload.notes,
        status="SCHEDULED",
        payment_status="PENDING",
        amount_paid_cents=0,
        payment_method_label="Pay at collection",
        transaction_id=None,
        reminder_enabled=True
    )
    db.add(pickup)
    db.flush()

    # Create Invoice
    fee = sum(item["priceCents"] for item in items) / 100
    invoice = Invoice(
        patient_id=current_patient.id,
        amount=fee,
        status="Pending",
        payment_mode="Pay at collection",
        transaction_id=pickup.transaction_id,
        service_date=collection_date
    )
    db.add(invoice)
    db.flush()

    db.add_all([InvoiceItem(
        invoice_id=invoice.id,
        service_name=f"Home Sample Collection: {item['title']}",
        quantity=1,
        unit_price=item["priceCents"] / 100,
    ) for item in items])

    # Alert
    alert = MobilePatientAlert(
        patient_id=current_patient.id,
        title="Sample Pickup Scheduled",
        message=f"Collection requested for {payload.pickupDateIso} ({payload.timeWindow}). Follow the laboratory preparation instructions.",
        alert_type="BLOOD_PICKUP",
        scheduled_time_label=payload.timeWindow,
        is_urgent=False
    )
    db.add(alert)

    db.commit()
    db.refresh(pickup)

    return {
        "id": pickup.id,
        "testPanelTitle": pickup.test_panel_title,
        "testCodes": pickup.test_codes,
        "fastingRequired": pickup.fasting_required,
        "pickupDateIso": pickup.pickup_date_iso,
        "pickupDateLabel": pickup.pickup_date_label,
        "timeWindow": pickup.time_window,
        "address": pickup.address,
        "notes": pickup.notes,
        "status": pickup.status,
        "paymentStatus": pickup.payment_status,
        "amountPaidCents": pickup.amount_paid_cents,
        "paymentMethodLabel": pickup.payment_method_label,
        "transactionId": pickup.transaction_id,
        "reminderEnabled": pickup.reminder_enabled,
        "createdAtMillis": int(pickup.created_at.timestamp() * 1000)
    }

def _format_lis_report(report: LISPatientReport) -> dict:
    biomarkers = []
    for result in report.resultsSnapshot:
        flag = (result.flag or "").strip().upper()
        if flag in {"HIGH", "LOW", "CRITICAL", "ABNORMAL"}:
            flag = "ATTENTION"
        elif flag not in {"NORMAL", "BORDERLINE"}:
            flag = "UNASSESSED"
        biomarkers.append({
            "name": result.testName,
            "displayValue": str(result.value) if result.value is not None else "Not recorded",
            "unit": result.unit or "",
            "refRange": result.referenceRange or "Not recorded",
            "minRef": None, "maxRef": None,
            "numericValue": _finite_numeric_value(result.value), "status": flag,
        })
    flags = {biomarker["status"] for biomarker in biomarkers}
    overall = next((flag for flag in ("ATTENTION", "BORDERLINE", "UNASSESSED") if flag in flags), None)
    return {
        "id": f"LIS-REP-{report.id}",
        "panelName": biomarkers[0]["name"] if len(biomarkers) == 1 else f"Lab report {report.accessionNumber}",
        "category": "Diagnostic Testing", "orderedByDoctor": "Not recorded",
        "reportDateLabel": report.releasedAt.strftime("%b %d, %Y"),
        "reportDateIso": report.releasedAt.date().isoformat(),
        "labFacility": "LIS", "overallStatus": overall or ("NORMAL" if flags else "UNASSESSED"),
        "doctorSummary": "", "serializedBiomarkers": "", "biomarkers": biomarkers,
    }


def _finite_numeric_value(value: str | float | None) -> float | None:
    try:
        number = float(value)
    except (ValueError, TypeError):
        return None
    return number if math.isfinite(number) else None


@router.get("/reports")
def get_lab_reports(
    response: Response,
    current_patient: Patient = Depends(get_current_patient),
    db: Session = Depends(get_db),
    latest_only: bool = False,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int | None, Query(ge=1, le=50)] = None,
    test_name: Annotated[str | None, Query(min_length=1, max_length=250)] = None,
    unit: Annotated[str, Query(max_length=100)] = "",
):
    response.headers["Cache-Control"] = "no-store"
    history = test_name is not None
    page_size = 6 if history else 1 if latest_only else limit
    start = 0 if latest_only or history else offset
    end = start + page_size if page_size is not None else None
    try:
        if history:
            lis_reports = fetch_released_patient_reports(
                db, current_patient.id, report_params={"test_name": test_name, "unit": unit, "limit": 6})
        elif end is None:
            lis_reports = fetch_released_patient_reports(db, current_patient.id)
        else:
            lis_reports = []
            while len(lis_reports) < end:
                batch_size = min(100, end - len(lis_reports))
                batch = fetch_released_patient_reports(db, current_patient.id, report_params={
                    "offset": len(lis_reports), "limit": batch_size,
                })
                lis_reports.extend(batch[:batch_size])
                if len(batch) < batch_size:
                    break
    except HTTPException as error:
        raise HTTPException(status_code=502, detail="Could not load released lab reports.") from error
    query = completed_lab_results(db, current_patient.id).options(
        joinedload(LabResult.catalog).load_only(LabCatalog.min_value, LabCatalog.max_value, LabCatalog.unit),
        joinedload(LabResult.orderer).load_only(User.username),
    )
    if history:
        query = query.filter(
            func.lower(func.trim(LabResult.test_name)) == test_name.strip().lower(),
            func.trim(func.coalesce(LabResult.unit, "")) == unit.strip(),
        )
    reports = []
    for report in lis_reports:
        data = _format_lis_report(report)
        if history:
            for reading in data["biomarkers"]:
                if (reading["name"].strip().lower() == test_name.strip().lower()
                    and reading["unit"].strip() == unit.strip() and reading["numericValue"] is not None):
                    reports.append((report_recency(report.releasedAt), {**data, "biomarkers": [reading]}))
        else:
            reports.append((report_recency(report.releasedAt), data))
    results = query.yield_per(50) if history else (query.limit(end) if end is not None else query).all()
    matched_manual = 0
    for result in results:
        numeric = _finite_numeric_value(result.result_value)
        reported_at = result.result_date or result.ordered_date
        if history and (numeric is None or reported_at is None):
            continue
        catalog = result.catalog
        minimum = catalog.min_value if catalog else None
        maximum = catalog.max_value if catalog else None
        flag = "UNASSESSED"
        if numeric is not None and catalog and (result.unit or "").strip() == (catalog.unit or "").strip() and (minimum is not None or maximum is not None):
            flag = "ATTENTION" if ((minimum is not None and numeric < minimum) or (maximum is not None and numeric > maximum)) else "NORMAL"
        reports.append((report_recency(reported_at), {
            "id": f"EMR-REP-{result.id}", "panelName": result.test_name,
            "category": "Diagnostic Testing",
            "orderedByDoctor": f"Dr. {result.orderer.username}" if result.orderer else "Not recorded",
            "reportDateLabel": reported_at.strftime("%b %d, %Y") if reported_at else "Not recorded",
            "reportDateIso": reported_at.date().isoformat() if reported_at else "",
            "labFacility": "Clinic laboratory", "overallStatus": flag,
            "doctorSummary": result.notes or "",
            "serializedBiomarkers": "",
            "biomarkers": [{"name": result.test_name, "displayValue": result.result_value,
                "unit": result.unit or "", "refRange": result.reference_range or "Not recorded",
                "minRef": minimum, "maxRef": maximum, "numericValue": numeric, "status": flag}]
        }))
        if history:
            matched_manual += 1
            if matched_manual == 6:
                break
    reports.sort(key=lambda entry: entry[0], reverse=True)
    return [report for _, report in reports[start:end]]
