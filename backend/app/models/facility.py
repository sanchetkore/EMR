from sqlalchemy import Column, Integer, String, Text, DateTime
from datetime import datetime
from app.core.database import Base

class Facility(Base):
    __tablename__ = "facilities"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    address = Column(Text, nullable=True)
    city = Column(String, nullable=True)
    state = Column(String, nullable=True)
    zip_code = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    operating_hours = Column(String, nullable=True) # e.g. "Mon-Fri 8am-5pm"
    is_active = Column(Integer, default=1) # 1=Active, 0=Inactive
    created_at = Column(DateTime, default=datetime.utcnow)
