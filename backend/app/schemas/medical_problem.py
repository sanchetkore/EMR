from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime

class MedicalProblemBase(BaseModel):
    patient_id: int
    title: str
    icd_code: Optional[str] = None
    onset_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[str] = "Active"
    notes: Optional[str] = None

class MedicalProblemCreate(MedicalProblemBase):
    pass

class MedicalProblem(MedicalProblemBase):
    id: int
    created_at: datetime
    class Config:
        orm_mode = True
