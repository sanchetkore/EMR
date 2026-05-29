from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from app.core.database import get_db
from app.models.lab_result import LabResult, LabCatalog
from app.models.clinical import Invoice, InvoiceItem
from app.schemas.lab_result import LabResult as LabResultSchema, LabResultCreate, LabCatalog as LabCatalogSchema, LabCatalogCreate
from app.api.deps import RequirePermission

router = APIRouter()

@router.get("/lab_catalog", response_model=List[LabCatalogSchema], dependencies=[Depends(RequirePermission("view_clinical"))])
def get_lab_catalog(db: Session = Depends(get_db)):
    return db.query(LabCatalog).all()

@router.post("/lab_catalog", response_model=LabCatalogSchema, dependencies=[Depends(RequirePermission("manage_clinical"))])
def create_lab_catalog_item(catalog_item: LabCatalogCreate, db: Session = Depends(get_db)):
    db_item = LabCatalog(**catalog_item.dict())
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

@router.get("/patients/{patient_id}/lab_results", response_model=List[LabResultSchema], dependencies=[Depends(RequirePermission("view_clinical"))])
def get_lab_results(patient_id: int, db: Session = Depends(get_db)):
    return db.query(LabResult).filter(LabResult.patient_id == patient_id).all()

@router.get("/patients/{patient_id}/lab_results/history", response_model=List[LabResultSchema], dependencies=[Depends(RequirePermission("view_clinical"))])
def get_lab_results_history(patient_id: int, test_name: Optional[str] = None, limit: int = 6, db: Session = Depends(get_db)):
    query = db.query(LabResult).filter(LabResult.patient_id == patient_id)
    if test_name:
        query = query.filter(LabResult.test_name == test_name)
    return query.order_by(LabResult.ordered_date.desc()).limit(limit).all()

@router.post("/lab_results", response_model=LabResultSchema, dependencies=[Depends(RequirePermission("manage_clinical"))])
def create_lab_result(lab_result: LabResultCreate, db: Session = Depends(get_db)):
    db_lab = LabResult(**lab_result.dict())
    db.add(db_lab)
    db.commit()
    db.refresh(db_lab)
    return db_lab

@router.get("/lab_results/{lab_id}", response_model=LabResultSchema, dependencies=[Depends(RequirePermission("view_clinical"))])
def get_lab_result(lab_id: int, db: Session = Depends(get_db)):
    db_lab = db.query(LabResult).filter(LabResult.id == lab_id).first()
    if not db_lab:
        raise HTTPException(status_code=404, detail="Lab Result not found")
    return db_lab

@router.put("/lab_results/{lab_id}", response_model=LabResultSchema, dependencies=[Depends(RequirePermission("manage_clinical"))])
def update_lab_result(lab_id: int, lab_update: LabResultCreate, db: Session = Depends(get_db)):
    db_lab = db.query(LabResult).filter(LabResult.id == lab_id).first()
    if not db_lab:
        raise HTTPException(status_code=404, detail="Lab Result not found")
    
    for var, value in vars(lab_update).items():
        setattr(db_lab, var, value)
        
    if lab_update.status == "Completed" and not db_lab.result_date:
        db_lab.result_date = datetime.utcnow()
        
        # Phase 7: Automated Billing Integration
        final_cost = db_lab.cost
        if final_cost is None and db_lab.catalog_id:
            catalog_item = db.query(LabCatalog).filter(LabCatalog.id == db_lab.catalog_id).first()
            if catalog_item:
                final_cost = catalog_item.price
        
        if final_cost is not None and final_cost > 0:
            # Find an active Pending invoice
            invoice = db.query(Invoice).filter(Invoice.patient_id == db_lab.patient_id, Invoice.status == "Pending").first()
            if not invoice:
                invoice = Invoice(patient_id=db_lab.patient_id, amount=0.0, status="Pending")
                db.add(invoice)
                db.commit()
                db.refresh(invoice)
            
            invoice_item = InvoiceItem(
                invoice_id=invoice.id,
                service_name=f"Lab Test: {db_lab.test_name}",
                quantity=1,
                unit_price=final_cost
            )
            db.add(invoice_item)
            invoice.amount = (invoice.amount or 0.0) + final_cost
            
    db.commit()
    db.refresh(db_lab)
    return db_lab
