from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class LabCatalogBase(BaseModel):
    name: str
    description: Optional[str] = None
    price: Optional[float] = 0.0
    is_active: Optional[bool] = True

class LabCatalogCreate(LabCatalogBase):
    pass

class LabCatalog(LabCatalogBase):
    id: int
    class Config:
        orm_mode = True


class LabResultBase(BaseModel):
    patient_id: int
    encounter_id: Optional[int] = None
    catalog_id: Optional[int] = None
    test_name: str
    cost: Optional[float] = None
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
