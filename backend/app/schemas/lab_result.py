from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class LabResultBase(BaseModel):
    patient_id: int
    encounter_id: Optional[int] = None
    test_name: str
    result_value: Optional[str] = None
    unit: Optional[str] = None
    reference_range: Optional[str] = None
    status: Optional[str] = "Pending"
    ordered_by: Optional[int] = None
    result_date: Optional[datetime] = None
    notes: Optional[str] = None

class LabResultCreate(LabResultBase):
    pass

class LabResult(LabResultBase):
    id: int
    ordered_date: datetime
    class Config:
        orm_mode = True
