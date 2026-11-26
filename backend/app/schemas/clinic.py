from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any

class BaseSettings(BaseModel):
    model_config = ConfigDict(extra='allow')

class SendPrescriptionSettings(BaseSettings):
    whatsapp: bool = False

class FollowupReminderSettings(BaseSettings):
    sms: bool = False
    whatsapp: bool = False
    days_early: int = 1

class LabReportSettings(BaseSettings):
    whatsapp: bool = False

class AppointmentScheduleSettings(BaseSettings):
    sms: bool = False
    whatsapp: bool = False

class NextAppointmentScheduleSettings(BaseSettings):
    sms: bool = False
    whatsapp: bool = False

class TreatmentReminderSettings(BaseSettings):
    sms: bool = False
    whatsapp: bool = False

class NotificationSettings(BaseSettings):
    send_prescription: Optional[SendPrescriptionSettings] = Field(default_factory=SendPrescriptionSettings)
    send_followup_reminder: Optional[FollowupReminderSettings] = Field(default_factory=FollowupReminderSettings)
    send_lab_report: Optional[LabReportSettings] = Field(default_factory=LabReportSettings)
    appointment_schedule: Optional[AppointmentScheduleSettings] = Field(default_factory=AppointmentScheduleSettings)
    next_appointment_schedule: Optional[NextAppointmentScheduleSettings] = Field(default_factory=NextAppointmentScheduleSettings)
    treatment_reminder: Optional[TreatmentReminderSettings] = Field(default_factory=TreatmentReminderSettings)
    messaging_api_key: Optional[str] = Field(default=None, exclude=True)
    sms_sender_id: Optional[str] = None

class ClinicProfileBase(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    support_email: Optional[str] = None
    phone: Optional[str] = None
    whatsapp: Optional[str] = None
    website: Optional[str] = None
    app_link: Optional[str] = None
    notification_settings: Optional[NotificationSettings] = None

class ClinicProfileUpdate(ClinicProfileBase):
    pass

class ClinicProfile(ClinicProfileBase):
    id: int
    logo_path: Optional[str] = None
    is_messaging_authenticated: bool = False

    class Config:
        from_attributes = True

class MessagingAuthInput(BaseModel):
    email: str
    password: str
    expires_in: Optional[str] = "30d"
