"""
SMS Messaging Service
Sends SMS messages via the external messaging provider API using the DLT route.
Uses background tasks to avoid blocking HTTP responses.
"""
import os
import json
import urllib.request
import urllib.error
import logging
from datetime import datetime, date

logging.basicConfig(level=logging.INFO)

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.clinic import ClinicProfile
from app.models.patient import Patient
from app.models.user import User

logger = logging.getLogger(__name__)


def _get_messaging_base_url() -> str:
    base_url = os.environ.get("MESSAGING_API_BASE_URL", "").rstrip("/")
    if not base_url:
        return ""
    if not base_url.startswith("http"):
        base_url = f"http://{base_url}"
    return base_url


def _get_clinic_settings(db: Session):
    """Returns (api_key, notification_settings, clinic_name) or (None, None, None)."""
    profile = db.query(ClinicProfile).filter(ClinicProfile.id == 1).first()
    if not profile or not profile.notification_settings:
        return None, None, None
    api_key = profile.notification_settings.get("messaging_api_key")
    return api_key, profile.notification_settings, profile.name


def _send_sms(base_url: str, api_key: str, template_id: str, message_id: str, sender_id: str, phone: str, variables_values: str):
    """POST to /api/v1/messages/sms to send a message."""
    endpoint = f"{base_url}/api/v1/messages/sms"
    body = {
        "route": "dlt",
        "template_id": template_id,
        "variables_values": variables_values,
        "sender_id": sender_id,
        "message": message_id,
        "numbers": phone
    }

    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=payload,
        headers={"x-api-key": api_key, "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            logger.info("SMS message accepted")
            return res_data
    except urllib.error.HTTPError as e:
        logger.error("SMS send failed (%s)", e.code)
    except Exception as e:
        logger.error("SMS send failed (%s)", type(e).__name__)


def _format_phone(contact_number: str) -> str:
    """Clean phone number (SMS provider does not require country code)."""
    if not contact_number:
        return ""
    phone = contact_number.strip().replace(" ", "").replace("-", "").replace("+", "")
    # For SMS, if it accidentally has 91 and is 12 digits, we might want to strip it,
    # but based on the instruction: "for sms thats not required"
    # we just won't prefix 91 if it's 10 digits.
    if len(phone) == 12 and phone.startswith("91"):
        phone = phone[2:]
    return phone


def send_appointment_sms(patient_id: int, doctor_id: int, appointment_time: datetime):
    """
    Sends Appointment Schedule SMS.
    Fixed order: patient_name | doctor_name | date | time
    """
    db = SessionLocal()
    try:
        base_url = _get_messaging_base_url()
        if not base_url:
            return

        api_key, settings, clinic_name = _get_clinic_settings(db)
        if not api_key or not settings:
            return

        app_sched_settings = settings.get("appointment_schedule", {})
        if not app_sched_settings.get("sms"):
            return

        template_id = app_sched_settings.get("sms_template_id")
        message_id = app_sched_settings.get("sms_message_id")
        sender_id = settings.get("sms_sender_id")

        if not template_id or not message_id or not sender_id:
            logger.warning("SMS settings incomplete for appointment_schedule")
            return

        patient = db.query(Patient).filter(Patient.id == patient_id).first()
        doctor = db.query(User).filter(User.id == doctor_id).first()

        if not patient or not doctor or not patient.contact_number:
            return

        phone = _format_phone(patient.contact_number)

        patient_name = f"{patient.first_name} {patient.last_name or ''}".strip()
        doctor_name = doctor.username
        app_date = appointment_time.strftime("%d/%m/%Y")
        app_time_str = appointment_time.strftime("%I:%M %p")

        variables_values = f"{patient_name}|{doctor_name}|{app_date}|{app_time_str}"

        _send_sms(base_url, api_key, template_id, message_id, sender_id, phone, variables_values)

    finally:
        db.close()


def send_prescription_sms(patient_id: int, doctor_id: int):
    """
    Sends Prescription SMS.
    Fixed order: patient_name | doctor_name
    """
    db = SessionLocal()
    try:
        base_url = _get_messaging_base_url()
        if not base_url:
            return

        api_key, settings, clinic_name = _get_clinic_settings(db)
        if not api_key or not settings:
            return

        presc_settings = settings.get("send_prescription", {})
        if not presc_settings.get("sms"):
            return

        template_id = presc_settings.get("sms_template_id")
        message_id = presc_settings.get("sms_message_id")
        sender_id = settings.get("sms_sender_id")

        if not template_id or not message_id or not sender_id:
            return

        patient = db.query(Patient).filter(Patient.id == patient_id).first()
        doctor = db.query(User).filter(User.id == doctor_id).first()

        if not patient or not doctor or not patient.contact_number:
            return

        phone = _format_phone(patient.contact_number)
        patient_name = f"{patient.first_name} {patient.last_name or ''}".strip()
        doctor_name = doctor.username

        variables_values = f"{patient_name}|{doctor_name}"

        _send_sms(base_url, api_key, template_id, message_id, sender_id, phone, variables_values)

    finally:
        db.close()


def send_lab_report_sms(patient_id: int):
    """
    Sends Lab Report SMS.
    Fixed order: patient_name | clinic_name
    """
    db = SessionLocal()
    try:
        base_url = _get_messaging_base_url()
        if not base_url:
            return

        api_key, settings, clinic_name = _get_clinic_settings(db)
        if not api_key or not settings:
            return

        lab_settings = settings.get("send_lab_report", {})
        if not lab_settings.get("sms"):
            return

        template_id = lab_settings.get("sms_template_id")
        message_id = lab_settings.get("sms_message_id")
        sender_id = settings.get("sms_sender_id")

        if not template_id or not message_id or not sender_id:
            return

        patient = db.query(Patient).filter(Patient.id == patient_id).first()
        if not patient or not patient.contact_number:
            return

        phone = _format_phone(patient.contact_number)
        patient_name = f"{patient.first_name} {patient.last_name or ''}".strip()

        variables_values = f"{patient_name}|{clinic_name or 'Our Clinic'}"

        _send_sms(base_url, api_key, template_id, message_id, sender_id, phone, variables_values)

    finally:
        db.close()


def send_followup_reminder_sms(patient_id: int, doctor_id: int, followup_date: date):
    """
    Sends Followup Reminder SMS.
    Fixed order: patient_name | doctor_name | followup_date
    """
    db = SessionLocal()
    try:
        base_url = _get_messaging_base_url()
        if not base_url:
            return

        api_key, settings, clinic_name = _get_clinic_settings(db)
        if not api_key or not settings:
            return

        remind_settings = settings.get("send_followup_reminder", {})
        if not remind_settings.get("sms"):
            return

        template_id = remind_settings.get("sms_template_id")
        message_id = remind_settings.get("sms_message_id")
        sender_id = settings.get("sms_sender_id")

        if not template_id or not message_id or not sender_id:
            return

        patient = db.query(Patient).filter(Patient.id == patient_id).first()
        doctor = db.query(User).filter(User.id == doctor_id).first()

        if not patient or not doctor or not patient.contact_number:
            return

        phone = _format_phone(patient.contact_number)
        patient_name = f"{patient.first_name} {patient.last_name or ''}".strip()
        doctor_name = doctor.username
        f_date = followup_date.strftime("%d/%m/%Y")

        variables_values = f"{patient_name}|{doctor_name}|{f_date}"

        _send_sms(base_url, api_key, template_id, message_id, sender_id, phone, variables_values)

    finally:
        db.close()
