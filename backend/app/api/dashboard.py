from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta, time
from app.core.database import get_db
from app.models.lab_result import LabResult, LabCatalog
from app.models.clinical import Invoice, InvoiceItem
from app.models.patient import Appointment, AppointmentTypeConfig
from app.api.deps import RequirePermission

router = APIRouter()

def get_stats_for_period(db: Session, start_date: datetime, end_date: datetime):
    # Appointments (Consultations)
    apt_patients = db.query(Appointment.patient_id).filter(
        Appointment.appointment_time >= start_date,
        Appointment.appointment_time <= end_date
    ).all()
    
    # Lab Results (Blood Tests)
    lab_patients = db.query(LabResult.patient_id).filter(
        LabResult.ordered_date >= start_date,
        LabResult.ordered_date <= end_date
    ).all()
    
    # Fetch catalogs
    app_type_names = [t[0].lower() for t in db.query(AppointmentTypeConfig.name).all()]
    lab_catalog_names = [l[0].lower() for l in db.query(LabCatalog.name).all()]
    
    # Query all invoice items in period
    invoice_items = db.query(InvoiceItem).join(Invoice).filter(
        Invoice.created_at >= start_date,
        Invoice.created_at <= end_date
    ).all()
    
    consultation_revenue = 0.0
    lab_revenue = 0.0
    others_revenue = 0.0
    
    for item in invoice_items:
        amount = item.unit_price * item.quantity
        s_name = (item.service_name or "").lower()
        
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
        
    return {
        "total_patients": len(set([p[0] for p in apt_patients] + [p[0] for p in lab_patients])),
        "consultations": {
            "patients": len(set([p[0] for p in apt_patients])),
            "total_appointments": len(apt_patients),
            "revenue": float(consultation_revenue)
        },
        "blood_tests": {
            "patients": len(set([p[0] for p in lab_patients])),
            "total_tests": len(lab_patients),
            "revenue": float(lab_revenue)
        },
        "others": {
            "revenue": float(others_revenue)
        }
    }

@router.get("/stats", dependencies=[Depends(RequirePermission("view_dashboard"))])
def get_dashboard_stats(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    
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
        "today": get_stats_for_period(db, today_start, today_end),
        "this_week": get_stats_for_period(db, week_start, week_end),
        "this_month": get_stats_for_period(db, month_start, month_end)
    }
