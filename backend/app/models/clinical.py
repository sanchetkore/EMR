from sqlalchemy import Column, Integer, String, Text, Float, ForeignKey, DateTime, Enum, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base
import enum



class Vitals(Base):
    __tablename__ = "vitals"
    id = Column(Integer, primary_key=True, index=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), unique=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), index=True)
    bp = Column(String, nullable=True) # e.g. 120/80
    sugar = Column(Float, nullable=True)
    pulse = Column(Integer, nullable=True)
    weight = Column(Float, nullable=True) # in kg
    height = Column(Float, nullable=True) # in cm
    bmi = Column(Float, nullable=True)
    
    appointment = relationship("Appointment", back_populates="vitals")
    patient = relationship("Patient")

class Consultation(Base):
    __tablename__ = "consultations"
    id = Column(Integer, primary_key=True, index=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), unique=True)
    history = Column(Text, nullable=True)
    complaints = Column(Text, nullable=True)
    analysis = Column(Text, nullable=True)
    prescription = Column(Text, nullable=True)
    advice = Column(Text, nullable=True)
    
    appointment = relationship("Appointment", back_populates="consultation")

class TemplateType(str, enum.Enum):
    PRESCRIPTION = "prescription"
    ADVICE = "advice"
    OTHER = "other"

class Template(Base):
    __tablename__ = "templates"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    type = Column(String) # TemplateType
    content = Column(Text, nullable=True)
    
    items = relationship("TemplateItem", back_populates="template", cascade="all, delete-orphan")

class TemplateItem(Base):
    __tablename__ = "template_items"
    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("templates.id"), index=True)
    molecule = Column(String)
    morning = Column(String, nullable=True)
    afternoon = Column(String, nullable=True)
    evening = Column(String, nullable=True)
    night = Column(String, nullable=True)
    when = Column(String, nullable=True) # e.g. Before food, After food
    details = Column(String, nullable=True)

    template = relationship("Template", back_populates="items")

class Invoice(Base):
    __tablename__ = "invoices"
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), index=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), index=True)
    amount = Column(Float)
    status = Column(String, default="Pending") # Pending, Paid, Cancelled
    created_at = Column(DateTime, default=datetime.utcnow)
    
    patient = relationship("Patient")
    appointment = relationship("Appointment")
    items = relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan")

class InvoiceItem(Base):
    __tablename__ = "invoice_items"
    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), index=True)
    service_name = Column(String)
    quantity = Column(Integer, default=1)
    unit_price = Column(Float)
    
    invoice = relationship("Invoice", back_populates="items")
