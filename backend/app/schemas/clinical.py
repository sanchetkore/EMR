from pydantic import BaseModel
from typing import Optional, List
from app.schemas.patient import Appointment

class VitalsBase(BaseModel):
    appointment_id: int
    patient_id: int
    bp: Optional[str] = None
    sugar: Optional[float] = None
    pulse: Optional[int] = None
    weight: Optional[float] = None
    height: Optional[float] = None
    bmi: Optional[float] = None

class VitalsCreate(VitalsBase):
    pass

class Vitals(VitalsBase):
    id: int
    class Config:
        orm_mode = True

class ConsultationBase(BaseModel):
    appointment_id: int
    history: Optional[str] = None
    complaints: Optional[str] = None
    analysis: Optional[str] = None
    prescription: Optional[str] = None
    advice: Optional[str] = None

class ConsultationCreate(ConsultationBase):
    pass

class Consultation(ConsultationBase):
    id: int
    class Config:
        orm_mode = True

class TemplateItemBase(BaseModel):
    molecule: str
    morning: Optional[str] = None
    afternoon: Optional[str] = None
    evening: Optional[str] = None
    night: Optional[str] = None
    when: Optional[str] = None
    details: Optional[str] = None

class TemplateItemCreate(TemplateItemBase):
    pass

class TemplateItem(TemplateItemBase):
    id: int
    class Config:
        orm_mode = True

class TemplateBase(BaseModel):
    name: str
    type: str # prescription, advice, allergy, etc.
    content: Optional[str] = None

class TemplateCreate(TemplateBase):
    items: List[TemplateItemCreate] = []

class Template(TemplateBase):
    id: int
    items: List[TemplateItem] = []
    class Config:
        orm_mode = True

class InvoiceItemBase(BaseModel):
    service_name: str
    quantity: Optional[int] = 1
    unit_price: float

class InvoiceItemCreate(InvoiceItemBase):
    pass

class InvoiceItem(InvoiceItemBase):
    id: int
    invoice_id: int
    class Config:
        orm_mode = True

class InvoiceBase(BaseModel):
    patient_id: int
    appointment_id: int
    amount: float
    status: Optional[str] = "Pending"

class InvoiceCreate(InvoiceBase):
    items: Optional[list[InvoiceItemCreate]] = []

class Invoice(InvoiceBase):
    id: int
    items: list[InvoiceItem] = []
    class Config:
        orm_mode = True

class BillSuggestionItem(BaseModel):
    service_name: str
    quantity: int = 1
    unit_price: float
    total_price: float

class BillSuggestion(BaseModel):
    appointment_id: int
    patient_id: int
    items: List[BillSuggestionItem] = []
    total_amount: float
