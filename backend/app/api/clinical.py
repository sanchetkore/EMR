from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.clinical import Vitals, Consultation, Invoice, InvoiceItem, Template, TemplateItem
from app.schemas.clinical import Vitals as VitalsSchema, VitalsCreate, Consultation as ConsultationSchema, ConsultationCreate, Template as TemplateSchema, TemplateCreate
from app.api.deps import RequirePermission

router = APIRouter()

@router.post("/vitals", response_model=VitalsSchema, dependencies=[Depends(RequirePermission("manage_clinical"))])
def create_vitals(vitals: VitalsCreate, db: Session = Depends(get_db)):
    # Calculate BMI if weight and height are provided
    if vitals.weight and vitals.height:
        # height in cm, weight in kg. BMI = weight / (height/100)^2
        height_m = vitals.height / 100.0
        vitals.bmi = vitals.weight / (height_m ** 2)
        
    db_vitals = Vitals(**vitals.dict())
    db.add(db_vitals)
    db.commit()
    db.refresh(db_vitals)
    return db_vitals

@router.get("/vitals/{appointment_id}", response_model=VitalsSchema, dependencies=[Depends(RequirePermission("view_clinical"))])
def get_vitals(appointment_id: int, db: Session = Depends(get_db)):
    vitals = db.query(Vitals).filter(Vitals.appointment_id == appointment_id).first()
    if not vitals:
        raise HTTPException(status_code=404, detail="Vitals not found")
    return vitals

@router.put("/vitals/{vitals_id}", response_model=VitalsSchema, dependencies=[Depends(RequirePermission("manage_clinical"))])
def update_vitals(vitals_id: int, vitals_update: VitalsCreate, db: Session = Depends(get_db)):
    db_vitals = db.query(Vitals).filter(Vitals.id == vitals_id).first()
    if not db_vitals:
        raise HTTPException(status_code=404, detail="Vitals not found")
    
    for var, value in vars(vitals_update).items():
        setattr(db_vitals, var, value)
        
    if db_vitals.weight and db_vitals.height:
        height_m = db_vitals.height / 100.0
        db_vitals.bmi = db_vitals.weight / (height_m ** 2)
        
    db.commit()
    db.refresh(db_vitals)
    return db_vitals

@router.post("/consultations", response_model=ConsultationSchema, dependencies=[Depends(RequirePermission("manage_clinical"))])
def create_consultation(consultation: ConsultationCreate, db: Session = Depends(get_db)):
    db_consultation = Consultation(**consultation.dict())
    db.add(db_consultation)
    db.commit()
    db.refresh(db_consultation)
    return db_consultation

@router.get("/templates", response_model=list[TemplateSchema], dependencies=[Depends(RequirePermission("view_templates"))])
def get_templates(db: Session = Depends(get_db)):
    return db.query(Template).all()

@router.post("/templates", response_model=TemplateSchema, dependencies=[Depends(RequirePermission("manage_templates"))])
def create_template(template: TemplateCreate, db: Session = Depends(get_db)):
    template_data = template.dict(exclude={"items"})
    db_template = Template(**template_data)
    
    for item in template.items:
        db_item = TemplateItem(**item.dict())
        db_template.items.append(db_item)
        
    db.add(db_template)
    db.commit()
    db.refresh(db_template)
    return db_template

@router.get("/consultations/{appointment_id}", response_model=ConsultationSchema, dependencies=[Depends(RequirePermission("view_clinical"))])
def get_consultation(appointment_id: int, db: Session = Depends(get_db)):
    consultation = db.query(Consultation).filter(Consultation.appointment_id == appointment_id).first()
    if not consultation:
        raise HTTPException(status_code=404, detail="Consultation not found")
    return consultation

@router.put("/consultations/{consultation_id}", response_model=ConsultationSchema, dependencies=[Depends(RequirePermission("manage_clinical"))])
def update_consultation(consultation_id: int, consultation_update: ConsultationCreate, db: Session = Depends(get_db)):
    db_consultation = db.query(Consultation).filter(Consultation.id == consultation_id).first()
    if not db_consultation:
        raise HTTPException(status_code=404, detail="Consultation not found")
    
    for var, value in vars(consultation_update).items():
        setattr(db_consultation, var, value)
        
    db.commit()
    db.refresh(db_consultation)
    return db_consultation

@router.put("/templates/{template_id}", response_model=TemplateSchema, dependencies=[Depends(RequirePermission("manage_templates"))])
def update_template(template_id: int, template_update: TemplateCreate, db: Session = Depends(get_db)):
    db_template = db.query(Template).filter(Template.id == template_id).first()
    if not db_template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    template_data = template_update.dict(exclude={"items"})
    for var, value in template_data.items():
        setattr(db_template, var, value)
        
    # Rebuild items
    db.query(TemplateItem).filter(TemplateItem.template_id == template_id).delete()
    for item in template_update.items:
        db_item = TemplateItem(**item.dict(), template_id=template_id)
        db.add(db_item)
        
    db.commit()
    db.refresh(db_template)
    return db_template

@router.delete("/templates/{template_id}", dependencies=[Depends(RequirePermission("manage_templates"))])
def delete_template(template_id: int, db: Session = Depends(get_db)):
    db_template = db.query(Template).filter(Template.id == template_id).first()
    if not db_template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    db.delete(db_template)
    db.commit()
    return {"detail": "Template deleted successfully"}
