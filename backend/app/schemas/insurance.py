from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime

class InsuranceBase(BaseModel):
    patient_id: int
    provider: str
    policy_number: str
    group_number: Optional[str] = None
    copay: Optional[float] = 0.0
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[str] = "Active"

class InsuranceCreate(InsuranceBase):
    pass

class Insurance(InsuranceBase):
    id: int
    created_at: datetime
    class Config:
        orm_mode = True
