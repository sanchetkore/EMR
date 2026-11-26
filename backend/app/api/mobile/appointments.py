from app.api.mobile.clock import clinic_now, clinic_timezone
from datetime import datetime, date, time
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_

from app.core.database import get_db
from app.models.patient import Patient, Appointment, AppointmentTypeConfig
from app.models.user import User, Role
from app.api.mobile.doctors import available_doctor_slots
from app.models.clinical import Invoice, InvoiceItem
from app.models.mobile import MobilePatientAlert, MobilePaymentRecord
from app.api.mobile.deps import get_current_patient

router = APIRouter(prefix="/appointments", tags=["mobile-appointments"])

class BookAppointmentRequest(BaseModel):
    doctorId: str = Field(pattern=r"^[0-9]{1,9}$")
    doctorName: Optional[str] = None
    doctorSpecialty: Optional[str] = None
    doctorAvatarKey: Optional[str] = "dr_elena"
    clinicRoom: Optional[str] = "Consultation Suite"
    visitType: str = "IN_CLINIC"
    dateIso: str  # YYYY-MM-DD
    dayLabel: Optional[str] = None
    timeSlot: str  # e.g. "10:15 AM"
    reasonForVisit: Optional[str] = Field(default="", max_length=2000)
    amountPaidCents: int = 0
    paymentMethodLabel: str = "Pay at clinic"
    transactionId: Optional[str] = None

def parse_slot_time(time_slot_str: str) -> time:
    try:
        # Expected formats: "10:15 AM", "02:30 PM"
        dt = datetime.strptime(time_slot_str.strip().upper(), "%I:%M %p")
        return dt.time()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid appointment time")

def map_appointment_response(appt: Appointment, current_patient: Patient, invoice=None) -> dict:
    doc = appt.doctor
    doc_name = f"Dr. {doc.username.capitalize()}" if doc else "Dr. Physician"

    date_iso = appt.appointment_time.strftime("%Y-%m-%d")
    day_label = appt.appointment_time.strftime("%a, %b %d")
    time_slot = appt.appointment_time.strftime("%I:%M %p")

    # Map status
    status_map = {
        "Scheduled": "UPCOMING",
        "Ongoing": "UPCOMING",
        "Completed": "COMPLETED",
        "Cancelled": "CANCELLED"
    }
    mapped_status = status_map.get(appt.status, "UPCOMING")

    return {
        "id": appt.id,
        "doctorId": str(appt.doctor_id) if appt.doctor_id else "1",
        "doctorName": doc_name,
        "doctorSpecialty": "Clinic physician",
        "doctorAvatarKey": "dr_elena",
        "clinicRoom": "Confirm at reception",
        "visitType": "IN_CLINIC",
        "dateIso": date_iso,
        "dayLabel": day_label,
        "timeSlot": time_slot,
        "reasonForVisit": appt.reason_for_visit or "",
        "status": mapped_status,
        "paymentStatus": "PAID" if invoice and invoice.status == "Paid" else "PENDING",
        "amountPaidCents": round(invoice.amount * 100) if invoice and invoice.status == "Paid" else 0,
        "paymentMethodLabel": invoice.payment_mode if invoice else "Pay at clinic",
        "transactionId": (invoice.transaction_id or "") if invoice else "",
        "tokenNumber": appt.token_number or f"T-{appt.id}",
        "reminderEnabled": True,
        "startsAtMillis": int(appt.appointment_time.replace(tzinfo=clinic_timezone()).timestamp() * 1000),
        "createdAtMillis": int(appt.appointment_time.timestamp() * 1000)
    }

@router.get("/")
def get_my_appointments(
    current_patient: Patient = Depends(get_current_patient),
    db: Session = Depends(get_db),
    next_only: bool = False,
):
    query = db.query(Appointment).options(
        joinedload(Appointment.doctor).load_only(User.username),
    ).filter(
        Appointment.patient_id == current_patient.id
    )
    if next_only:
        query = query.filter(
            Appointment.appointment_time > clinic_now(),
            or_(Appointment.status.is_(None), Appointment.status.notin_(("Completed", "Cancelled"))),
        ).order_by(Appointment.appointment_time, Appointment.id).limit(1)
    else:
        query = query.order_by(Appointment.appointment_time.desc())
    appts = query.all()

    invoices = db.query(Invoice).filter(Invoice.patient_id == current_patient.id, Invoice.appointment_id.in_([a.id for a in appts])).all() if appts else []
    by_appointment = {invoice.appointment_id: invoice for invoice in invoices}
    return [map_appointment_response(a, current_patient, by_appointment.get(a.id)) for a in appts]

@router.post("/")
def book_appointment(
    payload: BookAppointmentRequest,
    current_patient: Patient = Depends(get_current_patient),
    db: Session = Depends(get_db)
):
    try:
        booking_date = datetime.strptime(payload.dateIso, "%Y-%m-%d").date()
        if booking_date.isoformat() != payload.dateIso:
            raise ValueError("Non-canonical appointment date")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format, expected YYYY-MM-DD")

    booking_time = parse_slot_time(payload.timeSlot)
    appointment_dt = datetime.combine(booking_date, booking_time)

    if not payload.doctorId.isdigit():
        raise HTTPException(status_code=400, detail="Invalid doctor")
    doc_id = int(payload.doctorId)
    # Lock the doctor row so concurrent mobile bookings re-check availability serially.
    doctor = db.query(User).join(Role).filter(User.id == doc_id, Role.name == "Doctor", User.is_active == True).with_for_update().first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
    if payload.amountPaidCents or payload.transactionId:
        raise HTTPException(status_code=400, detail="Online payments are not enabled for bookings")
    if payload.timeSlot not in available_doctor_slots(db, doc_id, booking_date):
        raise HTTPException(status_code=409, detail="This appointment time is unavailable. Choose another time.")

    # Generate token number for the day
    start_of_day = datetime.combine(booking_date, datetime.min.time())
    end_of_day = datetime.combine(booking_date, datetime.max.time())
    count = db.query(Appointment).filter(
        Appointment.appointment_time >= start_of_day,
        Appointment.appointment_time <= end_of_day
    ).count()
    token = f"T-{(count + 1):02d}"

    # Get appointment type
    apt_type = db.query(AppointmentTypeConfig).filter(AppointmentTypeConfig.is_active == 1).first()

    new_appt = Appointment(
        patient_id=current_patient.id,
        doctor_id=doc_id,
        appointment_type_id=apt_type.id if apt_type else None,
        appointment_time=appointment_dt,
        status="Scheduled",
        token_number=token,
        reason_for_visit=(payload.reasonForVisit or "").strip()
    )
    db.add(new_appt)
    db.flush()

    # Create Invoice for billing
    fee = float(apt_type.rate or 0) if apt_type else 0.0
    invoice = Invoice(
        patient_id=current_patient.id,
        amount=fee,
        status="Pending",
        payment_mode="Pay at clinic",
        transaction_id=None,
        appointment_id=new_appt.id,
        service_date=booking_date
    )
    db.add(invoice)
    db.flush()

    invoice_item = InvoiceItem(
        invoice_id=invoice.id,
        service_name=f"Consultation with Dr. {doctor.username.capitalize()} (Token: {token})",
        quantity=1,
        unit_price=fee
    )
    db.add(invoice_item)

    # Add notification alert
    alert = MobilePatientAlert(
        patient_id=current_patient.id,
        title="Appointment Confirmed",
        message=f"Confirmed for {payload.dateIso} at {payload.timeSlot} with Dr. {doctor.username.capitalize()} (Token {token}).",
        alert_type="VISIT_REMINDER",
        scheduled_time_label=f"Token {token}",
        is_urgent=False
    )
    db.add(alert)

    db.commit()
    db.refresh(new_appt)

    return map_appointment_response(new_appt, current_patient, invoice)

@router.put("/{appointment_id}/cancel")
def cancel_appointment(
    appointment_id: int,
    current_patient: Patient = Depends(get_current_patient),
    db: Session = Depends(get_db)
):
    appt = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.patient_id == current_patient.id
    ).first()

    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    if appt.status == "Cancelled":
        return {"status": "SUCCESS", "message": "Appointment already cancelled"}
    if appt.status != "Scheduled" or appt.appointment_time <= clinic_now():
        raise HTTPException(status_code=409, detail="Only future scheduled appointments can be cancelled")
    appt.status = "Cancelled"
    db.query(Invoice).filter(
        Invoice.appointment_id == appt.id,
        Invoice.patient_id == current_patient.id,
        Invoice.status == "Pending",
    ).update({"status": "Cancelled"})
    db.commit()
    return {"status": "SUCCESS", "message": "Appointment cancelled successfully"}
