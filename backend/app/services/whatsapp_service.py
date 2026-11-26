"""
WhatsApp Messaging Service
Sends WhatsApp messages via the external messaging provider API.
Uses background tasks to avoid blocking HTTP responses.
"""
import os
import json
import urllib.request
import urllib.error
import logging

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



def _send_whatsapp(base_url: str, api_key: str, template_id: str, phone: str, variables: dict, media_url: str = None, header_variables: dict = None):
    """POST to /api/v1/messages/whatsapp to send a message."""
    endpoint = f"{base_url}/api/v1/messages/whatsapp"
    body = {
        "template_id": template_id,
        "to": phone,
        "variables": variables,
    }
    if header_variables:
        body["header_variables"] = header_variables
    if media_url:
        body["media_url"] = media_url
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
            logger.info("WhatsApp message accepted")
            return res_data
    except urllib.error.HTTPError as e:
        logger.error("WhatsApp send failed (%s)", e.code)
    except Exception as e:
        logger.error("WhatsApp send failed (%s)", type(e).__name__)


def _format_phone(contact_number: str) -> str:
    """Ensure phone number includes country code 91."""
    if not contact_number:
        return ""
    phone = contact_number.strip().replace(" ", "").replace("-", "").replace("+", "")
    if len(phone) == 10:
        phone = f"91{phone}"
    return phone


# ─── Public Background Task Functions ────────────────────────────────────────────

def send_appointment_whatsapp(patient_id: int, doctor_id: int, appointment_time):
    """Background task: send appointment confirmation via WhatsApp."""
    """
    Sends Appointment Schedule WhatsApp notification.
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
        if not app_sched_settings.get("whatsapp"):
            return

        template_id = app_sched_settings.get("whatsapp_template_id")
        var_map = app_sched_settings.get("whatsapp_variable_map", {})

        if not template_id:
            logger.warning("WhatsApp template ID missing for appointment_schedule")
            return

        patient = db.query(Patient).filter(Patient.id == patient_id).first()
        doctor = db.query(User).filter(User.id == doctor_id).first()

        if not patient or not doctor or not patient.contact_number:
            return

        phone = _format_phone(patient.contact_number)

        internal_vars = {
            "patient_name": f"{patient.first_name} {patient.last_name or ''}".strip(),
            "doctor_name": doctor.username,
            "appointment_date": appointment_time.strftime("%d/%m/%Y"),
            "appointment_time": appointment_time.strftime("%I:%M %p"),
            "clinic_name": clinic_name or "Our Clinic"
        }

        variables = {}
        for tmpl_var, internal_key in var_map.items():
            variables[tmpl_var] = internal_vars.get(internal_key, "")

        header_variables = {"clinic_name": clinic_name} if clinic_name else {}

        media_url_field = app_sched_settings.get("whatsapp_media_url")
        media_url = internal_vars.get(media_url_field) if media_url_field else None

        _send_whatsapp(base_url, api_key, template_id, phone, variables, media_url=media_url, header_variables=header_variables)

    finally:
        db.close()


def send_prescription_whatsapp(patient_id: int, doctor_id: int, prescription_id: int):
    """
    Sends Prescription WhatsApp notification.
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
        if not presc_settings.get("whatsapp"):
            return

        template_id = presc_settings.get("whatsapp_template_id")
        var_map = presc_settings.get("whatsapp_variable_map", {})

        if not template_id:
            return

        patient = db.query(Patient).filter(Patient.id == patient_id).first()
        doctor = db.query(User).filter(User.id == doctor_id).first()

        if not patient or not doctor or not patient.contact_number:
            return

        phone = _format_phone(patient.contact_number)

        clinic_profile = db.query(ClinicProfile).filter(ClinicProfile.id == 1).first()
        app_link = clinic_profile.app_link.rstrip("/") if clinic_profile and clinic_profile.app_link else ""
        prescription_pdf_url = f"{app_link}/print/prescription/{prescription_id}" if app_link else ""

        internal_vars = {
            "patient_name": f"{patient.first_name} {patient.last_name or ''}".strip(),
            "doctor_name": doctor.username,
            "clinic_name": clinic_name or "Our Clinic",
            "prescription_pdf_url": prescription_pdf_url
        }

        variables = {}
        for tmpl_var, internal_key in var_map.items():
            variables[tmpl_var] = internal_vars.get(internal_key, "")

        header_variables = {"clinic_name": clinic_name} if clinic_name else {}

        media_url_field = presc_settings.get("whatsapp_media_url")
        media_url = internal_vars.get(media_url_field) if media_url_field else None

        _send_whatsapp(base_url, api_key, template_id, phone, variables, media_url=media_url, header_variables=header_variables)

    finally:
        db.close()


def send_lab_report_whatsapp(patient_id: int, lab_result_id: int):
    """
    Sends Lab Report WhatsApp notification.
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
        if not lab_settings.get("whatsapp"):
            return

        template_id = lab_settings.get("whatsapp_template_id")
        var_map = lab_settings.get("whatsapp_variable_map", {})

        if not template_id:
            return

        patient = db.query(Patient).filter(Patient.id == patient_id).first()
        if not patient or not patient.contact_number:
            return

        phone = _format_phone(patient.contact_number)

        clinic_profile = db.query(ClinicProfile).filter(ClinicProfile.id == 1).first()
        app_link = clinic_profile.app_link.rstrip("/") if clinic_profile and clinic_profile.app_link else ""
        lab_report_pdf_url = f"{app_link}/print/lab/{lab_result_id}" if app_link else ""

        internal_vars = {
            "patient_name": f"{patient.first_name} {patient.last_name or ''}".strip(),
            "clinic_name": clinic_name or "Our Clinic",
            "lab_report_pdf_url": lab_report_pdf_url
        }

        variables = {}
        for tmpl_var, internal_key in var_map.items():
            variables[tmpl_var] = internal_vars.get(internal_key, "")

        header_variables = {"clinic_name": clinic_name} if clinic_name else {}

        media_url_field = lab_settings.get("whatsapp_media_url")
        media_url = internal_vars.get(media_url_field) if media_url_field else None

        _send_whatsapp(base_url, api_key, template_id, phone, variables, media_url=media_url, header_variables=header_variables)

    finally:
        db.close()


def send_followup_reminder_whatsapp(patient_id: int, doctor_id: int, followup_date):
    """
    Sends Followup Reminder WhatsApp notification.
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
        if not remind_settings.get("whatsapp"):
            return

        template_id = remind_settings.get("whatsapp_template_id")
        var_map = remind_settings.get("whatsapp_variable_map", {})

        if not template_id:
            return

        patient = db.query(Patient).filter(Patient.id == patient_id).first()
        doctor = db.query(User).filter(User.id == doctor_id).first()

        if not patient or not doctor or not patient.contact_number:
            return

        phone = _format_phone(patient.contact_number)

        internal_vars = {
            "patient_name": f"{patient.first_name} {patient.last_name or ''}".strip(),
            "doctor_name": doctor.username,
            "clinic_name": clinic_name or "Our Clinic",
            "followup_date": followup_date.strftime("%d/%m/%Y")
        }

        variables = {}
        for tmpl_var, internal_key in var_map.items():
            variables[tmpl_var] = internal_vars.get(internal_key, "")

        header_variables = {"clinic_name": clinic_name} if clinic_name else {}

        media_url_field = remind_settings.get("whatsapp_media_url")
        media_url = internal_vars.get(media_url_field) if media_url_field else None

        _send_whatsapp(base_url, api_key, template_id, phone, variables, media_url=media_url, header_variables=header_variables)

    finally:
        db.close()
