from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.clinical import Invoice, InvoiceItem
from app.models.patient import Appointment
from app.models.lab_result import LabResult
from app.schemas.clinical import Invoice as InvoiceSchema, InvoiceCreate, BillSuggestion, BillSuggestionItem
from app.api.deps import RequirePermission
from typing import Optional
from datetime import date, datetime
from sqlalchemy import cast, Date

router = APIRouter()

@router.post("/", response_model=InvoiceSchema, dependencies=[Depends(RequirePermission("manage_billing"))])
def create_invoice(invoice: InvoiceCreate, db: Session = Depends(get_db)):
    invoice_data = invoice.dict(exclude={"items"})
    db_invoice = Invoice(**invoice_data)
    db.add(db_invoice)
    db.commit()
    db.refresh(db_invoice)
    
    for item in invoice.items:
        db_item = InvoiceItem(**item.dict(), invoice_id=db_invoice.id)
        db.add(db_item)
    
    db.commit()
    db.refresh(db_invoice)
    return db_invoice

@router.get("/", response_model=list[InvoiceSchema], dependencies=[Depends(RequirePermission("view_billing"))])
def get_invoices(
    patient_id: Optional[int] = None, 
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Invoice)
    if patient_id:
        query = query.filter(Invoice.patient_id == patient_id)
    if start_date:
        query = query.filter(cast(Invoice.created_at, Date) >= start_date)
    if end_date:
        query = query.filter(cast(Invoice.created_at, Date) <= end_date)
    return query.all()

@router.get("/{invoice_id}", response_model=InvoiceSchema, dependencies=[Depends(RequirePermission("view_billing"))])
def get_invoice(invoice_id: int, db: Session = Depends(get_db)):
    db_invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not db_invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return db_invoice

@router.put("/{invoice_id}", response_model=InvoiceSchema, dependencies=[Depends(RequirePermission("manage_billing"))])
def update_invoice(invoice_id: int, invoice_update: InvoiceCreate, db: Session = Depends(get_db)):
    db_invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not db_invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
        
    db_invoice.amount = invoice_update.amount
    if invoice_update.status:
        db_invoice.status = invoice_update.status
    if invoice_update.appointment_id is not None:
        db_invoice.appointment_id = invoice_update.appointment_id
        
    # Rebuild items
    db.query(InvoiceItem).filter(InvoiceItem.invoice_id == invoice_id).delete()
    db.flush()
    
    if invoice_update.items:
        for item in invoice_update.items:
            db_item = InvoiceItem(**item.dict(), invoice_id=db_invoice.id)
            db.add(db_item)
            
    db.commit()
    db.refresh(db_invoice)
    return db_invoice

@router.put("/{invoice_id}/status", response_model=InvoiceSchema, dependencies=[Depends(RequirePermission("manage_billing"))])
def update_invoice_status(invoice_id: int, status: str, db: Session = Depends(get_db)):
    db_invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not db_invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    db_invoice.status = status
    db.commit()
    db.refresh(db_invoice)
    return db_invoice

@router.delete("/{invoice_id}", dependencies=[Depends(RequirePermission("delete_billing"))])
def delete_invoice(invoice_id: int, db: Session = Depends(get_db)):
    db_invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not db_invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    db.query(InvoiceItem).filter(InvoiceItem.invoice_id == invoice_id).delete()
    db.delete(db_invoice)
    db.commit()
    return {"detail": "Invoice and all associated items deleted successfully"}

@router.get("/suggest/{appointment_id}", response_model=BillSuggestion, dependencies=[Depends(RequirePermission("manage_billing"))])
def suggest_bill(appointment_id: int, db: Session = Depends(get_db)):
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
        
    items = []
    total = 0.0
    
    # 1. Add Appointment Consultation Fee
    if appointment.appointment_type:
        rate = appointment.appointment_type.rate
        items.append(BillSuggestionItem(
            service_name=f"Consultation ({appointment.appointment_type.name})",
            quantity=1,
            unit_price=rate,
            total_price=rate
        ))
        total += rate
        
    # 2. Find any Lab Tests ordered during this appointment's encounter
    # We find the encounter for this appointment first
    if appointment.consultation:
        encounter_id = appointment.consultation.encounter_id
        labs = db.query(LabResult).filter(LabResult.encounter_id == encounter_id).all()
        for lab in labs:
            if lab.catalog and lab.catalog.price > 0:
                price = lab.catalog.price
                items.append(BillSuggestionItem(
                    service_name=f"Lab Test: {lab.test_name}",
                    quantity=1,
                    unit_price=price,
                    total_price=price
                ))
                total += price
                
    return BillSuggestion(
        appointment_id=appointment.id,
        patient_id=appointment.patient_id,
        items=items,
        total_amount=total
    )
