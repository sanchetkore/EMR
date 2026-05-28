from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class DocumentBase(BaseModel):
    patient_id: int
    encounter_id: Optional[int] = None
    type: str
    title: str
    file_path: str
    uploaded_by: int
    notes: Optional[str] = None

class DocumentCreate(DocumentBase):
    pass

class Document(DocumentBase):
    id: int
    created_at: datetime
    class Config:
        orm_mode = True
