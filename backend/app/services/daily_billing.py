"""Daily service suggestions reconciled against existing invoice line items."""
from collections import defaultdict
from datetime import datetime, time, timedelta
from sqlalchemy import or_
from sqlalchemy.orm import selectinload
from app.models.patient import Appointment, Patient
from app.models.lab_result import LabResult
from app.models.clinical import Invoice


def daily_suggestions(db, service_date, patient_id=None):
    start = datetime.combine(service_date, time.min)
    end = start + timedelta(days=1)
    appointments = db.query(Appointment).options(selectinload(Appointment.appointment_type)).filter(
        Appointment.appointment_time >= start, Appointment.appointment_time < end,
        Appointment.status.in_(['Ongoing', 'Completed']),
    )
    labs = db.query(LabResult).options(selectinload(LabResult.catalog), selectinload(LabResult.combo)).filter(
        LabResult.ordered_date >= start, LabResult.ordered_date < end,
        LabResult.status.notin_(['Cancelled', 'Canceled']),
    )
    if patient_id is not None:
        appointments = appointments.filter(Appointment.patient_id == patient_id)
        labs = labs.filter(LabResult.patient_id == patient_id)
    appointments = appointments.order_by(Appointment.id).all()
    labs = labs.order_by(LabResult.id).all()
    services = defaultdict(list)
    appointment_ids = defaultdict(list)
    for appt in appointments:
        appointment_ids[appt.patient_id].append(appt.id)
        kind = appt.appointment_type
        services[appt.patient_id].append({
            'service_name': f'Consultation ({kind.name})' if kind else 'Consultation',
            'quantity': 1, 'unit_price': float(kind.rate or 0) if kind else 0,
            'price_missing': kind is None, 'appointment_id': appt.id,
        })
    packages = set()
    for lab in labs:
        if lab.combo_id:
            # A package produces several result rows for a single order.
            key = (lab.patient_id, lab.combo_id, lab.encounter_id, lab.ordered_date.replace(microsecond=0))
            if key in packages:
                continue
            packages.add(key)
            name = f'Lab Package: {lab.combo.name}' if lab.combo else f'Lab Package #{lab.combo_id}'
            price = lab.combo.price if lab.combo else None
        else:
            name = f'Lab Test: {lab.test_name}'
            price = lab.cost if lab.cost is not None else lab.catalog.price if lab.catalog else None
        services[lab.patient_id].append({'service_name': name, 'quantity': 1,
            'unit_price': float(price or 0), 'price_missing': price is None, 'appointment_id': None,
            'package_test_names': [f'Lab Test: {other.test_name}'.strip().casefold() for other in labs
                if lab.combo_id and other.combo_id == lab.combo_id and other.patient_id == lab.patient_id]})
    if not services:
        return []
    all_ids = [item for ids in appointment_ids.values() for item in ids]
    # Include linked invoices even when they were generated on another day.
    invoices = db.query(Invoice).options(selectinload(Invoice.items)).filter(
        Invoice.patient_id.in_(services), Invoice.status != 'Cancelled',
        or_(Invoice.service_date == service_date,
            (Invoice.service_date.is_(None)) & (Invoice.created_at >= start) & (Invoice.created_at < end),
            Invoice.appointment_id.in_(all_ids)),
    ).order_by(Invoice.id).all()
    patients = {p.id: p for p in db.query(Patient).filter(Patient.id.in_(services)).all()}
    result = []
    for pid, rows in services.items():
        existing = [i for i in invoices if i.patient_id == pid]
        billed = defaultdict(int)
        for invoice in existing:
            for item in invoice.items:
                billed[item.service_name.strip().casefold()] += item.quantity or 0
        due = []
        package_review = False
        for row in rows:
            name = row['service_name'].strip().casefold()
            # Older manual invoices may use the plain consultation label.
            if name.startswith('consultation (') and not billed[name] and billed['consultation']:
                billed['consultation'] -= 1
                continue
            if billed[name] > 0:
                billed[name] -= 1
            else:
                if any(billed[test_name] > 0 for test_name in row.get('package_test_names', [])):
                    package_review = True
                due.append(row)
        # Legacy invoices without line items cannot be safely matched automatically.
        review = package_review or any(not i.items for i in existing)
        patient = patients.get(pid)
        result.append({'patient_id': pid, 'patient_name': f'{patient.first_name} {patient.last_name}'.strip() if patient else f'Patient #{pid}',
            'opd_number': patient.opd_number if patient else None, 'service_date': service_date.isoformat(),
            'items': rows, 'unbilled_items': due, 'total_amount': round(sum(r['unit_price'] for r in due), 2),
            'existing_invoices': [{'id': i.id, 'status': i.status, 'amount': i.amount} for i in existing],
            'needs_review': review or any(r['price_missing'] for r in due),
            'status': 'Review required' if review else 'Already billed' if not due else 'Partially billed' if existing else 'Not billed'})
    return sorted(result, key=lambda r: (r['patient_name'].casefold(), r['patient_id']))
