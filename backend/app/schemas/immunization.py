from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime

class ImmunizationBase(BaseModel):
    patient_id: int
    vaccine_name: str
    administered_date: date
    lot_number: Optional[str] = None
    site: Optional[str] = None
    administered_by: Optional[int] = None
    notes: Optional[str] = None

class ImmunizationCreate(ImmunizationBase):
    pass

class Immunization(ImmunizationBase):
    id: int
    created_at: datetime
    class Config:
        orm_mode = True
