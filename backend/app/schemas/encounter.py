from pydantic import BaseModel, Field, model_validator
from typing import Optional, List
from app.schemas.prescription import PrescriptionItemCreate, Prescription
from app.schemas.patient import Appointment as AppointmentSchema
from datetime import datetime, date

class EncounterBase(BaseModel):
    patient_id: int
    doctor_id: int
    appointment_id: Optional[int] = None
    reason: Optional[str] = None
    notes: Optional[str] = None
    draft_orders: Optional[dict] = None
    quick_notes: Optional[str] = None
    advice: Optional[str] = None
    visit_number: Optional[int] = None
    status: Optional[str] = "Open"
    followup_days: Optional[int] = None
    followup_months: Optional[int] = None
    followup_date: Optional[date] = None

class EncounterCreate(EncounterBase):
    pass

class Encounter(EncounterBase):
    id: int
    version: int
    signed_at: Optional[datetime] = None
    signed_by_id: Optional[int] = None
    encounter_date: datetime
    created_at: datetime
    class Config:
        orm_mode = True

class VitalConfigurationBase(BaseModel):
    name: str
    data_type: str
    formula: Optional[str] = None
    is_active: Optional[bool] = True

class VitalConfiguration(VitalConfigurationBase):
    id: int
    class Config:
        orm_mode = True

class PatientVitalBase(BaseModel):
    vital_config_id: int
    value: Optional[str] = None

class PatientVital(PatientVitalBase):
    id: int
    encounter_id: int
    class Config:
        orm_mode = True

class VisitComplaintBase(BaseModel):
    complaint: str
    from_date: Optional[str] = None
    duration: Optional[str] = None

class VisitComplaint(VisitComplaintBase):
    id: int
    encounter_id: int
    class Config:
        orm_mode = True

class VisitDiagnosisBase(BaseModel):
    diagnosis: str
    date: Optional[str] = None

class VisitDiagnosis(VisitDiagnosisBase):
    id: int
    encounter_id: int
    class Config:
        orm_mode = True

class VisitTreatmentBase(BaseModel):
    treatment: str
    due_date: Optional[str] = None

class VisitTreatment(VisitTreatmentBase):
    id: int
    encounter_id: int
    class Config:
        orm_mode = True

class VisitLabOrderRequest(BaseModel):
    test_codes: List[str] = []
    package_codes: List[str] = []
    notes: Optional[str] = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def require_tests_or_packages(self):
        if not self.test_codes and not self.package_codes:
            raise ValueError("Select at least one laboratory test or package")
        return self


class VisitPayload(BaseModel):
    # Encounter core data
    patient_id: int
    doctor_id: int
    appointment_id: Optional[int] = None
    reason: Optional[str] = None
    notes: Optional[str] = None
    draft_orders: Optional[dict] = None
    quick_notes: Optional[str] = None
    advice: Optional[str] = None
    status: Optional[str] = "Open"
    followup_days: Optional[int] = None
    followup_months: Optional[int] = None
    followup_date: Optional[date] = None

    # Nested lists
    vitals: List[PatientVitalBase] = []
    complaints: List[VisitComplaintBase] = []
    diagnoses: List[VisitDiagnosisBase] = []
    treatments: List[VisitTreatmentBase] = []

    # Lab orders
    lab_test_catalogs: List[int] = [] # List of catalog IDs to order
    lis_order: Optional[VisitLabOrderRequest] = None

    # Prescriptions
    prescriptions: List[PrescriptionItemCreate] = []

class VisitUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    patient_id: Optional[int] = None
    doctor_id: Optional[int] = None
    appointment_id: Optional[int] = None
    reason: Optional[str] = None
    notes: Optional[str] = None
    draft_orders: Optional[dict] = None
    quick_notes: Optional[str] = None
    advice: Optional[str] = None
    status: Optional[str] = None
    followup_days: Optional[int] = None
    followup_months: Optional[int] = None
    followup_date: Optional[date] = None
    vitals: Optional[List[PatientVitalBase]] = None
    complaints: Optional[List[VisitComplaintBase]] = None
    diagnoses: Optional[List[VisitDiagnosisBase]] = None
    treatments: Optional[List[VisitTreatmentBase]] = None
    prescriptions: Optional[List[dict]] = None
    lab_test_catalogs: Optional[List[int]] = None
    lis_order: Optional[VisitLabOrderRequest] = None


class VisitLabOrderIntent(BaseModel):
    id: int
    encounter_id: int
    source_id: str
    connection_id: str
    test_codes: List[str]
    package_codes: List[str]
    status: str
    attempt_count: int
    remote_order_id: Optional[str] = None
    accession_number: Optional[str] = None
    last_error: Optional[str] = None

    class Config:
        from_attributes = True


class AmendmentCreate(BaseModel):
    reason: str = Field(min_length=3, max_length=255)
    note: str = Field(min_length=1)


class Amendment(BaseModel):
    id: int
    encounter_id: int
    author_id: int
    reason: str
    note: str
    created_at: datetime

    class Config:
        from_attributes = True

class VisitResponse(BaseModel):
    encounter: Encounter
    vitals: List[PatientVital]
    complaints: List[VisitComplaint]
    diagnoses: List[VisitDiagnosis]
    treatments: List[VisitTreatment]
    prescriptions: List[Prescription] = []
    lab_results: List[dict] = [] # Returning dicts or a new schema
    appointment: Optional[AppointmentSchema] = None
    amendments: List[Amendment] = []
    lab_order_intent: Optional[VisitLabOrderIntent] = None
    class Config:
        orm_mode = True

class FollowupResponse(BaseModel):
    encounter_id: int
    patient_id: int
    patient_name: str
    patient_phone: Optional[str] = None
    doctor_name: str
    last_visit_date: datetime
    followup_date: date
    followup_days: Optional[int] = None
    reason: Optional[str] = None
    visit_number: Optional[int] = None

    class Config:
        orm_mode = True
