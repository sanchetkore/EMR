from datetime import datetime
import os
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.models.patient import Patient
from app.models.clinical import Invoice
from app.models.mobile import MobilePaymentRecord, MobilePatientAlert
from app.api.mobile.deps import get_current_patient

router = APIRouter(prefix="/payments", tags=["mobile-payments"])

class CreateOrderRequest(BaseModel):
    amount_cents: int  # Amount in paise / cents
    category: str = "APPOINTMENT"  # APPOINTMENT, BLOOD_PICKUP, INVOICE
    reference_title: Optional[str] = "Clinical Service"
    currency: str = "INR"

class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: Optional[str] = None
    category: str = "APPOINTMENT"
    reference_title: Optional[str] = "Clinical Service"
    amount_cents: int
    insurance_saved_cents: int = 0

@router.get("/config")
def get_payment_config():
    """Exposes public Razorpay key for mobile SDK checkout."""
    return {
        "enabled": False,
        "currency": "INR",
        "merchant_name": "Aura Clinic & Diagnostics"
    }

@router.post("/create-order")
def create_payment_order(
    payload: CreateOrderRequest,
    current_patient: Patient = Depends(get_current_patient)
):
    raise HTTPException(status_code=503, detail="Online payments are not enabled. Please pay at the clinic.")

@router.post("/verify")
def verify_payment(
    payload: VerifyPaymentRequest,
    current_patient: Patient = Depends(get_current_patient),
    db: Session = Depends(get_db)
):
    raise HTTPException(status_code=503, detail="Online payments are not enabled. Please pay at the clinic.")

@router.get("/history")
def get_payment_history(
    current_patient: Patient = Depends(get_current_patient),
    db: Session = Depends(get_db)
):
    records = db.query(MobilePaymentRecord).filter(
        MobilePaymentRecord.patient_id == current_patient.id
    ).order_by(MobilePaymentRecord.created_at.desc()).all()


    payments = [
        {
            "id": r.id,
            "referenceTitle": r.reference_title,
            "category": r.category,
            "amountCents": r.amount_cents,
            "insuranceSavedCents": r.insurance_saved_cents,
            "paymentMethod": r.payment_method,
            "transactionId": r.transaction_id,
            "status": r.status,
            "timestampLabel": r.timestamp_label or r.created_at.strftime("%b %d, %Y • %I:%M %p"),
            "createdAtMillis": int(r.created_at.timestamp() * 1000)
        }
        for r in records
    ]
    # Receipts recorded by clinic staff are authoritative too.
    transactions = {r.transaction_id for r in records}
    invoices = db.query(Invoice).options(selectinload(Invoice.items)).filter(
        Invoice.patient_id == current_patient.id, Invoice.status == "Paid"
    ).all()
    for invoice in invoices:
        if invoice.transaction_id and invoice.transaction_id in transactions:
            continue
        payments.append({
            "id": -invoice.id,
            "referenceTitle": ", ".join(item.service_name for item in invoice.items) or f"Invoice #{invoice.id}",
            "category": "INVOICE", "amountCents": round((invoice.amount or 0) * 100),
            "insuranceSavedCents": 0, "paymentMethod": invoice.payment_mode,
            "transactionId": invoice.transaction_id or f"Invoice #{invoice.id}",
            "status": "SUCCEEDED", "timestampLabel": invoice.created_at.strftime("%b %d, %Y"),
            "createdAtMillis": int(invoice.created_at.timestamp() * 1000),
        })
    return sorted(payments, key=lambda item: item['createdAtMillis'], reverse=True)


@router.get("/invoices")
def get_invoices(
    current_patient: Patient = Depends(get_current_patient),
    db: Session = Depends(get_db),
    pending_only: bool = False,
):
    query = db.query(Invoice).options(selectinload(Invoice.items)).filter(Invoice.patient_id == current_patient.id)
    if pending_only:
        query = query.filter(Invoice.status == "Pending")
    invoices = query.order_by(Invoice.created_at.desc()).all()
    return [{"id": item.id, "amountCents": round((item.amount or 0) * 100), "status": item.status,
             "title": ", ".join(line.service_name for line in item.items) or f"Invoice #{item.id}"} for item in invoices]
