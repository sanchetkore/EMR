from sqlalchemy import Column, Integer, String, Text, DateTime
from datetime import datetime
from app.core.database import Base

class WhatsappTemplate(Base):
    __tablename__ = "whatsapp_templates"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    category = Column(String)
    language = Column(String)
    body = Column(Text)
    status = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
