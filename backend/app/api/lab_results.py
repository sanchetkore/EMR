from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import cast, Date, or_
from typing import List, Optional
from datetime import datetime, date as date_type
from app.core.database import get_db
from app.schemas.lab_result import LabResult as LabResultSchema, LabResultCreate, LabCatalog as LabCatalogSchema, LabCatalogCreate, LabOrderResponse, ComboLabTestSchema, ComboLabTestCreate, OrderComboPayload
from app.models.lab_result import LabResult, LabCatalog, ComboLabTest
from app.models.clinical import Invoice, InvoiceItem
from app.schemas.patient import Patient as PatientSchema
from app.api.deps import RequirePermission

router = APIRouter()

@router.get("/lab_results/lab_catalog", response_model=List[LabCatalogSchema], dependencies=[Depends(RequirePermission("view_clinical"))])
def get_lab_catalog(query: Optional[str] = None, db: Session = Depends(get_db)):
    db_query = db.query(LabCatalog)
    if query:
        db_query = db_query.filter(LabCatalog.name.ilike(f"%{query}%"))
    return db_query.all()

@router.post("/lab_results/lab_catalog", response_model=LabCatalogSchema, dependencies=[Depends(RequirePermission("manage_clinical"))])
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

@router.get("/patients/{patient_id}/lab_results/latest", response_model=List[LabResultSchema], dependencies=[Depends(RequirePermission("view_clinical"))])
def get_latest_lab_results(patient_id: int, db: Session = Depends(get_db)):
    """Fetch all lab results ordered on the most recent date for this patient."""
    latest_result = db.query(LabResult).filter(LabResult.patient_id == patient_id).order_by(LabResult.ordered_date.desc()).first()
    
    if not latest_result:
        return []
        
    latest_date = latest_result.ordered_date.date()
    
    return db.query(LabResult).filter(
        LabResult.patient_id == patient_id,
        cast(LabResult.ordered_date, Date) == latest_date
    ).all()

@router.get("/lab_results/by_date", response_model=List[LabOrderResponse], dependencies=[Depends(RequirePermission("view_clinical"))])
def get_lab_results_by_date(date: date_type, status: Optional[str] = None, db: Session = Depends(get_db)):
    """Fetch all lab results from a specific date across all patients."""
    query = db.query(LabResult).filter(
        or_(
            cast(LabResult.ordered_date, Date) == date,
            cast(LabResult.result_date, Date) == date
        )
    )
    if status:
        query = query.filter(LabResult.status == status)
    results = query.order_by(LabResult.ordered_date.desc()).all()
    
    response = []
    for r in results:
        patient_data = None
        if r.patient:
            patient_data = PatientSchema.model_validate(r.patient, from_attributes=True)
        response.append(LabOrderResponse(
            lab_result=LabResultSchema.model_validate(r, from_attributes=True),
            patient=patient_data
        ))
    return response

@router.get("/lab_results/orders/queue", response_model=List[LabOrderResponse], dependencies=[Depends(RequirePermission("view_clinical"))])
def get_lab_orders_queue(status: Optional[str] = "Pending", db: Session = Depends(get_db)):
    """Fetch a global queue of all lab orders/appointments across all patients."""
    query = db.query(LabResult)
    if status:
        query = query.filter(LabResult.status == status)
        
    results = query.order_by(LabResult.ordered_date.desc()).all()
    
    response = []
    for r in results:
        patient_data = None
        if r.patient:
            patient_data = PatientSchema.model_validate(r.patient, from_attributes=True)
            
        response.append(LabOrderResponse(
            lab_result=LabResultSchema.model_validate(r, from_attributes=True),
            patient=patient_data
        ))
    return response
@router.get("/lab_results/combo_catalog", response_model=List[ComboLabTestSchema], dependencies=[Depends(RequirePermission("view_clinical"))])
def get_combo_catalog(db: Session = Depends(get_db)):
    return db.query(ComboLabTest).all()

@router.post("/lab_results/combo_catalog", response_model=ComboLabTestSchema, dependencies=[Depends(RequirePermission("manage_clinical"))])
def create_combo_catalog_item(combo_item: ComboLabTestCreate, db: Session = Depends(get_db)):
    db_item = ComboLabTest(**combo_item.dict())
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

@router.put("/lab_results/combo_catalog/{combo_id}", response_model=ComboLabTestSchema, dependencies=[Depends(RequirePermission("manage_clinical"))])
def update_combo_catalog_item(combo_id: int, combo_update: ComboLabTestCreate, db: Session = Depends(get_db)):
    db_item = db.query(ComboLabTest).filter(ComboLabTest.id == combo_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Combo not found")
        
    for var, value in vars(combo_update).items():
        setattr(db_item, var, value)
        
    db.commit()
    db.refresh(db_item)
    return db_item

@router.delete("/lab_results/combo_catalog/{combo_id}", dependencies=[Depends(RequirePermission("manage_clinical"))])
def delete_combo_catalog_item(combo_id: int, db: Session = Depends(get_db)):
    db_item = db.query(ComboLabTest).filter(ComboLabTest.id == combo_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Combo not found")
        
    db.delete(db_item)
    db.commit()
    return {"detail": "Combo deleted successfully"}

@router.post("/lab_results/order_combo", response_model=List[LabResultSchema], dependencies=[Depends(RequirePermission("manage_clinical"))])
def order_combo(payload: OrderComboPayload, db: Session = Depends(get_db)):
    combo = db.query(ComboLabTest).filter(ComboLabTest.id == payload.combo_id).first()
    if not combo:
        raise HTTPException(status_code=404, detail="Combo not found")
        
    created_results = []
    
    for test_id in combo.test_ids:
        catalog_item = db.query(LabCatalog).filter(LabCatalog.id == test_id).first()
        if not catalog_item:
            continue # Skip invalid test IDs
            
        new_result = LabResult(
            patient_id=payload.patient_id,
            encounter_id=payload.encounter_id,
            catalog_id=catalog_item.id,
            test_name=catalog_item.name,
            status="Pending",
            ordered_by=payload.ordered_by,
            ordered_date=payload.ordered_date or datetime.utcnow()
        )
        db.add(new_result)
        created_results.append(new_result)
        
    db.commit()
    for result in created_results:
        db.refresh(result)
        
    return created_results

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
    db.commit()
    db.refresh(db_lab)
    return db_lab

@router.delete("/lab_results/{lab_id}", dependencies=[Depends(RequirePermission("manage_clinical"))])
def delete_lab_result(lab_id: int, db: Session = Depends(get_db)):
    db_lab = db.query(LabResult).filter(LabResult.id == lab_id).first()
    if not db_lab:
        raise HTTPException(status_code=404, detail="Lab Result not found")
        
    db.delete(db_lab)
    db.commit()
    return {"detail": "Lab Result deleted successfully"}
