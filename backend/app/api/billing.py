from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.clinical import Invoice
from app.schemas.clinical import Invoice as InvoiceSchema, InvoiceCreate
from app.api.deps import RequirePermission

router = APIRouter()

from typing import Optional
from app.models.clinical import Invoice, InvoiceItem

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

@router.get("/", response_model=list[InvoiceSchema], dependencies=[Depends(RequirePermission("manage_billing"))])
def get_invoices(patient_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(Invoice)
    if patient_id:
        query = query.filter(Invoice.patient_id == patient_id)
    return query.all()

@router.get("/{invoice_id}", response_model=InvoiceSchema, dependencies=[Depends(RequirePermission("manage_billing"))])
def get_invoice(invoice_id: int, db: Session = Depends(get_db)):
    db_invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not db_invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
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
    
    # Delete associated invoice items first to avoid foreign key constraint errors
    db.query(InvoiceItem).filter(InvoiceItem.invoice_id == invoice_id).delete()
    db.delete(db_invoice)
    db.commit()
    return {"detail": "Invoice and all associated items deleted successfully"}
