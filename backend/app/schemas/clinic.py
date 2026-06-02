from pydantic import BaseModel
from typing import Optional

class ClinicProfileBase(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    support_email: Optional[str] = None
    phone: Optional[str] = None
    whatsapp: Optional[str] = None
    website: Optional[str] = None
    app_link: Optional[str] = None

class ClinicProfileUpdate(ClinicProfileBase):
    pass

class ClinicProfile(ClinicProfileBase):
    id: int
    logo_path: Optional[str] = None

    class Config:
        from_attributes = True
