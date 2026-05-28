from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime

class MedicationBase(BaseModel):
    patient_id: int
    drug_name: str
    dosage: Optional[str] = None
    frequency: Optional[str] = None
    route: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    prescribed_by: Optional[int] = None
    status: Optional[str] = "Active"
    notes: Optional[str] = None

class MedicationCreate(MedicationBase):
    pass

class Medication(MedicationBase):
    id: int
    created_at: datetime
    class Config:
        orm_mode = True
