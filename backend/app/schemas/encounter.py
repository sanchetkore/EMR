from pydantic import BaseModel
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

class VisitPayload(BaseModel):
    # Encounter core data
    patient_id: int
    doctor_id: int
    appointment_id: Optional[int] = None
    reason: Optional[str] = None
    notes: Optional[str] = None
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
    
    # Prescriptions
    prescriptions: List[PrescriptionItemCreate] = []

class VisitUpdate(BaseModel):
    reason: Optional[str] = None
    notes: Optional[str] = None
    quick_notes: Optional[str] = None
    advice: Optional[str] = None
    status: Optional[str] = None
    followup_days: Optional[int] = None
    followup_months: Optional[int] = None
    followup_date: Optional[date] = None
    prescriptions: Optional[List[dict]] = None
    lab_test_catalogs: Optional[List[int]] = None

class VisitResponse(BaseModel):
    encounter: Encounter
    vitals: List[PatientVital]
    complaints: List[VisitComplaint]
    diagnoses: List[VisitDiagnosis]
    treatments: List[VisitTreatment]
    prescriptions: List[Prescription] = []
    lab_results: List[dict] = [] # Returning dicts or a new schema
    appointment: Optional[AppointmentSchema] = None
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
