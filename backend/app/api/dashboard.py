from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func
from datetime import datetime, timedelta, time
from app.core.database import get_db
from app.models.lab_result import LabResult, LabCatalog
from app.models.clinical import Invoice, InvoiceItem
from app.models.patient import Appointment, AppointmentTypeConfig
from app.api.deps import RequirePermission

router = APIRouter()

def get_stats_for_period(db: Session, start_date: datetime, end_date: datetime, app_type_names: list, lab_catalog_names: list):
    apt_stats = db.query(
        func.count(Appointment.id).label("total_appointments"),
        func.count(func.distinct(Appointment.patient_id)).label("unique_patients")
    ).filter(
        Appointment.appointment_time >= start_date,
        Appointment.appointment_time <= end_date
    ).first()

    lab_stats = db.query(
        func.count(LabResult.id).label("total_tests"),
        func.count(func.distinct(LabResult.patient_id)).label("unique_patients")
    ).filter(
        LabResult.ordered_date >= start_date,
        LabResult.ordered_date <= end_date
    ).first()

    # Total unique patients across both (approximate with sum, or we can just query it)
    # To get exact unique patients across both, we can UNION the patient IDs, but fetching distinct patients is fine.
    # For speed, let's use a union query for total distinct patients.
    apt_patients_q = db.query(Appointment.patient_id).filter(
        Appointment.appointment_time >= start_date,
        Appointment.appointment_time <= end_date
    )
    lab_patients_q = db.query(LabResult.patient_id).filter(
        LabResult.ordered_date >= start_date,
        LabResult.ordered_date <= end_date
    )
    total_patients = apt_patients_q.union(lab_patients_q).count()

    # Fetch all paid invoices with their items to ensure Revenue Breakdown exactly matches Payment Methods
    paid_invoices = db.query(Invoice).options(selectinload(Invoice.items)).filter(
        Invoice.created_at >= start_date,
        Invoice.created_at <= end_date,
        Invoice.status == "Paid"
    ).all()

    consultation_revenue = 0.0
    lab_revenue = 0.0
    others_revenue = 0.0

    for inv in paid_invoices:
        invoice_amount = float(inv.amount or 0.0)
        items_sum = sum(float(item.unit_price * item.quantity) for item in inv.items)

        # Any discrepancy between the stored invoice amount and the sum of its items
        # (or if the invoice has no items) goes into "others" so the total perfectly matches.
        discrepancy = invoice_amount - items_sum
        others_revenue += discrepancy

        for item in inv.items:
            s_name = (item.service_name or "").lower()
            amount = float(item.unit_price * item.quantity)

            is_consultation = False
            is_lab = False

            if s_name.startswith("consultation"):
                is_consultation = True
            else:
                for t_name in app_type_names:
                    if t_name in s_name:
                        is_consultation = True
                        break

            if not is_consultation:
                if s_name.startswith("lab test"):
                    is_lab = True
                else:
                    for l_name in lab_catalog_names:
                        if l_name in s_name:
                            is_lab = True
                            break

            if is_consultation:
                consultation_revenue += amount
            elif is_lab:
                lab_revenue += amount
            else:
                others_revenue += amount

    # Payment mode breakdown for Paid invoices
    payment_mode_data = db.query(
        Invoice.payment_mode,
        func.sum(Invoice.amount).label("total")
    ).filter(
        Invoice.created_at >= start_date,
        Invoice.created_at <= end_date,
        Invoice.status == "Paid"
    ).group_by(Invoice.payment_mode).all()

    payments = {
        "Cash": 0.0,
        "Card": 0.0,
        "UPI": 0.0,
        "Bank Transfer": 0.0,
        "Insurance": 0.0
    }
    for row in payment_mode_data:
        mode = row.payment_mode or "Cash"
        if mode not in payments:
            payments[mode] = 0.0
        payments[mode] += float(row.total or 0.0)

    return {
        "total_patients": total_patients,
        "consultations": {
            "patients": apt_stats.unique_patients or 0,
            "total_appointments": apt_stats.total_appointments or 0,
            "revenue": consultation_revenue
        },
        "blood_tests": {
            "patients": lab_stats.unique_patients or 0,
            "total_tests": lab_stats.total_tests or 0,
            "revenue": lab_revenue
        },
        "others": {
            "revenue": others_revenue
        },
        "payment_modes": payments
    }

@router.get("/stats", dependencies=[Depends(RequirePermission("view_dashboard"))])
def get_dashboard_stats(db: Session = Depends(get_db)):
    now = datetime.utcnow()

    # Fetch catalogs ONCE
    app_type_names = [t[0].lower() for t in db.query(AppointmentTypeConfig.name).all()]
    lab_catalog_names = [l[0].lower() for l in db.query(LabCatalog.name).all()]

    # Today
    today_start = datetime.combine(now.date(), time.min)
    today_end = datetime.combine(now.date(), time.max)

    # This Week (Assuming week starts on Monday)
    week_start = datetime.combine(now.date() - timedelta(days=now.weekday()), time.min)
    week_end = today_end

    # This Month
    month_start = datetime.combine(now.date().replace(day=1), time.min)
    month_end = today_end

    return {
        "today": get_stats_for_period(db, today_start, today_end, app_type_names, lab_catalog_names),
        "this_week": get_stats_for_period(db, week_start, week_end, app_type_names, lab_catalog_names),
        "this_month": get_stats_for_period(db, month_start, month_end, app_type_names, lab_catalog_names)
    }
