from sqlalchemy import Column, Integer, String, Boolean
from app.core.database import Base

class Drug(Base):
    __tablename__ = "drugs"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    generic_name = Column(String, index=True, nullable=True)
    form = Column(String, nullable=True) # Tablet, Capsule, Syrup, etc.
    strength = Column(String, nullable=True) # 500mg
    manufacturer = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
