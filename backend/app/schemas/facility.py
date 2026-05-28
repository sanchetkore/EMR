from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class FacilityBase(BaseModel):
    name: str
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    operating_hours: Optional[str] = None
    is_active: Optional[int] = 1

class FacilityCreate(FacilityBase):
    pass

class Facility(FacilityBase):
    id: int
    created_at: datetime
    class Config:
        orm_mode = True
