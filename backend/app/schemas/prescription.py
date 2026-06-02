from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class PrescriptionItemBase(BaseModel):
    molecule: Optional[str] = ""
    name: Optional[str] = ""
    morning: Optional[str] = None
    afternoon: Optional[str] = None
    evening: Optional[str] = None
    night: Optional[str] = None
    when: Optional[str] = None
    details: Optional[str] = None

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
