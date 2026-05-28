from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class PrescriptionItemBase(BaseModel):
    drug_name: str
    dosage: str
    frequency: str
    duration: Optional[str] = None
    quantity: Optional[int] = None
    instructions: Optional[str] = None

class PrescriptionItemCreate(PrescriptionItemBase):
    pass

class PrescriptionItem(PrescriptionItemBase):
    id: int
    prescription_id: int
    class Config:
        orm_mode = True

class PrescriptionBase(BaseModel):
    patient_id: int
    encounter_id: Optional[int] = None
    doctor_id: int
    notes: Optional[str] = None

class PrescriptionCreate(PrescriptionBase):
    items: List[PrescriptionItemCreate] = []

class Prescription(PrescriptionBase):
    id: int
    date_prescribed: datetime
    items: List[PrescriptionItem] = []
    class Config:
        orm_mode = True
