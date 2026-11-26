"""
PDF Generation Service
Generates prescription and lab report PDFs matching the frontend print layout.
Uses fpdf2 (pure Python, no system deps).
"""
import os
import uuid
import logging
from datetime import datetime
from fpdf import FPDF

from sqlalchemy.orm import Session
from app.models.clinic import ClinicProfile
from app.models.patient import Patient
from app.models.user import User
from app.models.prescription import Prescription, PrescriptionItem
from app.models.lab_result import LabResult

logger = logging.getLogger(__name__)

TEMP_PDF_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "temp_pdfs")


def _ensure_temp_dir():
    os.makedirs(TEMP_PDF_DIR, exist_ok=True)


def _get_clinic(db: Session):
    return db.query(ClinicProfile).filter(ClinicProfile.id == 1).first()


def _calc_age(dob) -> str:
    if not dob:
        return ""
    today = datetime.utcnow().date()
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    return f"{age} yrs"


class EMRPdf(FPDF):
    """Custom PDF class with clinic header/footer."""

    def __init__(self, clinic=None):
        super().__init__()
        self.clinic = clinic
        self.set_auto_page_break(auto=True, margin=25)

    def header(self):
        c = self.clinic
        if not c:
            return

        # Clinic name
        self.set_font("Helvetica", "B", 16)
        self.cell(0, 8, c.name or "Clinic", align="C", new_x="LMARGIN", new_y="NEXT")

        # Address
        if c.address:
            self.set_font("Helvetica", "", 9)
            self.set_text_color(100, 100, 100)
            self.cell(0, 5, c.address, align="C", new_x="LMARGIN", new_y="NEXT")

        # Phone | Email
        contact_parts = []
        if c.phone:
            contact_parts.append(f"Phone: {c.phone}")
        if c.support_email:
            contact_parts.append(f"Email: {c.support_email}")
        if contact_parts:
            self.set_font("Helvetica", "", 8)
            self.set_text_color(130, 130, 130)
            self.cell(0, 5, "  |  ".join(contact_parts), align="C", new_x="LMARGIN", new_y="NEXT")

        # Separator line
        self.ln(3)
        self.set_draw_color(50, 50, 50)
        self.set_line_width(0.5)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(6)
        self.set_text_color(0, 0, 0)

    def footer(self):
        c = self.clinic
        self.set_y(-20)
        self.set_draw_color(180, 180, 180)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(3)

        parts = []
        if c and c.phone:
            parts.append(f"Phone: {c.phone}")
        if c and c.whatsapp:
            parts.append(f"WhatsApp: {c.whatsapp}")
        if c and c.support_email:
            parts.append(f"Email: {c.support_email}")
        if c and c.website:
            parts.append(f"Website: {c.website}")

        if parts:
            self.set_font("Helvetica", "", 7)
            self.set_text_color(160, 160, 160)
            self.cell(0, 4, "   ".join(parts), align="C")

    def _patient_info_bar(self, patient: Patient, date_str: str = "", time_str: str = ""):
        """Render patient info section."""
        y_start = self.get_y()

        # Background box
        self.set_fill_color(248, 250, 252)
        self.set_draw_color(226, 232, 240)
        self.rect(self.l_margin, y_start, self.w - self.l_margin - self.r_margin, 22, style="DF")

        # Left side: Patient info
        self.set_xy(self.l_margin + 4, y_start + 2)
        self.set_font("Helvetica", "B", 6)
        self.set_text_color(130, 130, 130)
        self.cell(60, 3, "PATIENT", new_x="LMARGIN", new_y="NEXT")

        self.set_x(self.l_margin + 4)
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(30, 41, 59)
        self.cell(90, 6, f"{patient.first_name} {patient.last_name}", new_x="LMARGIN", new_y="NEXT")

        info_parts = [patient.gender or ""]
        age = _calc_age(patient.dob)
        if age:
            info_parts.append(age)
        if patient.blood_group:
            info_parts.append(patient.blood_group)
        self.set_x(self.l_margin + 4)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(100, 116, 139)
        self.cell(90, 4, " | ".join(filter(None, info_parts)), new_x="LMARGIN", new_y="NEXT")

        if patient.opd_number:
            self.set_x(self.l_margin + 4)
            self.set_font("Courier", "", 7)
            self.set_text_color(130, 130, 130)
            self.cell(90, 4, f"OPD: {patient.opd_number}")

        # Right side: Date
        if date_str:
            self.set_xy(self.w - self.r_margin - 60, y_start + 2)
            self.set_font("Helvetica", "B", 6)
            self.set_text_color(130, 130, 130)
            self.cell(56, 3, "DATE", align="R", new_x="LMARGIN", new_y="NEXT")

            self.set_xy(self.w - self.r_margin - 60, y_start + 6)
            self.set_font("Helvetica", "B", 12)
            self.set_text_color(30, 41, 59)
            self.cell(56, 6, date_str, align="R", new_x="LMARGIN", new_y="NEXT")

            if time_str:
                self.set_xy(self.w - self.r_margin - 60, y_start + 13)
                self.set_font("Helvetica", "", 8)
                self.set_text_color(130, 130, 130)
                self.cell(56, 4, time_str, align="R")

        self.set_y(y_start + 26)
        self.set_text_color(0, 0, 0)


def generate_prescription_pdf(db: Session, prescription_id: int) -> str:
    """Generate a prescription PDF and return the file path."""
    _ensure_temp_dir()

    prescription = db.query(Prescription).filter(Prescription.id == prescription_id).first()
    if not prescription:
        raise ValueError(f"Prescription {prescription_id} not found")

    patient = db.query(Patient).filter(Patient.id == prescription.patient_id).first()
    doctor = db.query(User).filter(User.id == prescription.doctor_id).first()
    clinic = _get_clinic(db)

    pdf = EMRPdf(clinic=clinic)
    pdf.add_page()

    # Patient info
    dt = prescription.date_prescribed or datetime.utcnow()
    date_str = dt.strftime("%d/%m/%Y")
    time_str = dt.strftime("%I:%M %p")
    pdf._patient_info_bar(patient, date_str, time_str)

    # Rx header
    pdf.set_font("Times", "I", 36)
    pdf.set_text_color(200, 200, 200)
    pdf.cell(20, 12, "Rx", new_x="END")
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 12, "  PRESCRIPTION", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Table header
    col_widths = [10, 50, 40, 30, 20, 40]
    headers = ["#", "Medicine", "Dosage (M-A-E-N)", "When", "Days", "Notes"]
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(71, 85, 105)
    pdf.set_fill_color(241, 245, 249)
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 7, h, border=0, fill=True)
    pdf.ln()

    # Separator
    pdf.set_draw_color(203, 213, 225)
    pdf.set_line_width(0.4)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(2)

    # Table rows
    items = prescription.items or []
    for idx, item in enumerate(items):
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(148, 163, 184)
        pdf.cell(col_widths[0], 7, str(idx + 1))

        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(30, 41, 59)
        medicine_name = item.molecule or ""
        pdf.cell(col_widths[1], 7, medicine_name[:30])

        dosage = " - ".join([
            item.morning or "0",
            item.afternoon or "0",
            item.evening or "0",
            item.night or "0",
        ])
        pdf.set_font("Courier", "", 9)
        pdf.set_text_color(71, 85, 105)
        pdf.cell(col_widths[2], 7, dosage)

        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(71, 85, 105)
        pdf.cell(col_widths[3], 7, (item.when or "As directed")[:18])
        pdf.cell(col_widths[4], 7, str(item.duration_days) if item.duration_days is not None else "-")

        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(130, 130, 130)
        pdf.cell(col_widths[5], 7, (item.details or "-")[:25])
        pdf.ln()

        # Row separator
        pdf.set_draw_color(241, 245, 249)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())

    # Advice section
    if prescription.notes:
        pdf.ln(8)
        pdf.set_fill_color(248, 250, 252)
        pdf.set_draw_color(226, 232, 240)
        y_start = pdf.get_y()
        pdf.set_font("Helvetica", "B", 7)
        pdf.set_text_color(130, 130, 130)
        pdf.cell(0, 5, "ADVICE & INSTRUCTIONS", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(30, 41, 59)
        pdf.multi_cell(0, 5, prescription.notes)

    # Doctor signature
    pdf.ln(20)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(30, 41, 59)
    doctor_name = f"Dr. {doctor.username}" if doctor else "Dr. Attending Doctor"
    pdf.cell(0, 6, doctor_name, align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(130, 130, 130)
    pdf.cell(0, 4, "MEDICAL PRACTITIONER", align="R")

    # Save
    filename = f"prescription_{prescription_id}_{uuid.uuid4().hex[:8]}.pdf"
    filepath = os.path.join(TEMP_PDF_DIR, filename)
    pdf.output(filepath)
    logger.info(f"Generated prescription PDF: {filepath}")
    return filename


def generate_lab_report_pdf(db: Session, patient_id: int, lab_ids: list[int] = None) -> str:
    """Generate a lab report PDF for a patient's completed results.
    If lab_ids is provided, only include those specific results.
    Otherwise includes all completed results for the patient."""
    _ensure_temp_dir()

    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise ValueError(f"Patient {patient_id} not found")

    clinic = _get_clinic(db)

    query = db.query(LabResult).filter(
        LabResult.patient_id == patient_id,
        LabResult.status == "Completed"
    )
    if lab_ids:
        query = query.filter(LabResult.id.in_(lab_ids))
    lab_results = query.order_by(LabResult.result_date.desc()).all()

    if not lab_results:
        raise ValueError(f"No completed lab results for patient {patient_id}")

    pdf = EMRPdf(clinic=clinic)
    pdf.add_page()

    # Patient info
    result_date = lab_results[0].result_date or datetime.utcnow()
    date_str = result_date.strftime("%d/%m/%Y")
    pdf._patient_info_bar(patient, date_str)

    # Title
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 10, "LABORATORY REPORT", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # Table header
    col_widths = [55, 40, 50, 30]
    headers = ["Test Name", "Result", "Reference Range", "Unit"]
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(71, 85, 105)
    pdf.set_fill_color(241, 245, 249)
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 7, h, fill=True)
    pdf.ln()

    # Separator
    pdf.set_draw_color(203, 213, 225)
    pdf.set_line_width(0.4)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(2)

    # Result rows
    for lab in lab_results:
        is_out = _is_out_of_range(lab.result_value, lab.reference_range)

        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(30, 41, 59)
        pdf.cell(col_widths[0], 7, (lab.test_name or "")[:30])

        if is_out:
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(220, 38, 38)  # Red
            pdf.cell(col_widths[1], 7, f"{lab.result_value or ''} *")
        else:
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(30, 41, 59)
            pdf.cell(col_widths[1], 7, lab.result_value or "")

        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(col_widths[2], 7, (lab.reference_range or "")[:28])

        pdf.set_text_color(130, 130, 130)
        pdf.cell(col_widths[3], 7, (lab.unit or "")[:15])
        pdf.ln()

        pdf.set_draw_color(241, 245, 249)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())

    # Save
    filename = f"labreport_{patient_id}_{uuid.uuid4().hex[:8]}.pdf"
    filepath = os.path.join(TEMP_PDF_DIR, filename)
    pdf.output(filepath)
    logger.info(f"Generated lab report PDF: {filepath}")
    return filename


def _is_out_of_range(result_value: str, reference_range: str) -> bool:
    """Check if a lab result value is outside the reference range.
    Handles formats like '10-20', '< 5', '> 3'."""
    if not result_value or not reference_range:
        return False
    try:
        val = float(result_value.strip())
    except (ValueError, TypeError):
        return False

    ref = reference_range.strip()
    try:
        if "-" in ref:
            parts = ref.split("-")
            low = float(parts[0].strip())
            high = float(parts[1].strip())
            return val < low or val > high
        elif ref.startswith("<"):
            high = float(ref[1:].strip())
            return val >= high
        elif ref.startswith(">"):
            low = float(ref[1:].strip())
            return val <= low
    except (ValueError, IndexError):
        pass
    return False
