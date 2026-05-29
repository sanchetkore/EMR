from pydantic import BaseModel
from typing import Optional

class DrugBase(BaseModel):
    name: str
    generic_name: Optional[str] = None
    form: Optional[str] = None
    strength: Optional[str] = None
    manufacturer: Optional[str] = None
    is_active: Optional[bool] = True

class DrugCreate(DrugBase):
    pass

class Drug(DrugBase):
    id: int
    class Config:
        orm_mode = True
