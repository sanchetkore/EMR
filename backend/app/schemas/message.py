from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class MessageBase(BaseModel):
    receiver_id: int
    subject: str
    body: str
    patient_id: Optional[int] = None

class MessageCreate(MessageBase):
    pass

class Message(MessageBase):
    id: int
    sender_id: int
    status: str
    created_at: datetime
    class Config:
        orm_mode = True
