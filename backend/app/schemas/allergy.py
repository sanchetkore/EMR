from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime

class AllergyBase(BaseModel):
    patient_id: int
    allergen: str
    reaction: Optional[str] = None
    severity: Optional[str] = "Mild"
    onset_date: Optional[date] = None
    status: Optional[str] = "Active"
    notes: Optional[str] = None

class AllergyCreate(AllergyBase):
    pass

class Allergy(AllergyBase):
    id: int
    created_at: datetime
    class Config:
        orm_mode = True
