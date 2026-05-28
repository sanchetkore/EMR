from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class EncounterBase(BaseModel):
    patient_id: int
    doctor_id: int
    appointment_id: Optional[int] = None
    reason: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = "Open"

class EncounterCreate(EncounterBase):
    pass

class Encounter(EncounterBase):
    id: int
    encounter_date: datetime
    created_at: datetime
    class Config:
        orm_mode = True
