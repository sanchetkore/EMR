from sqlalchemy import Column, Integer, String, Text, JSON
from app.core.database import Base

class ClinicProfile(Base):
    __tablename__ = "clinic_profile"
    id = Column(Integer, primary_key=True, index=True, default=1)
    name = Column(String, nullable=True)
    address = Column(Text, nullable=True)
    support_email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    whatsapp = Column(String, nullable=True)
    website = Column(String, nullable=True)
    app_link = Column(String, nullable=True)
    logo_path = Column(String, nullable=True)
    notification_settings = Column(JSON, nullable=True)

    @property
    def is_messaging_authenticated(self) -> bool:
        if not self.notification_settings:
            return False
        return bool(self.notification_settings.get("messaging_api_key"))
