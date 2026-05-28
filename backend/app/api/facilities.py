from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.models.facility import Facility
from app.schemas.facility import Facility as FacilitySchema, FacilityCreate
from app.api.deps import RequirePermission

router = APIRouter()

@router.get("/", response_model=List[FacilitySchema])
def get_facilities(db: Session = Depends(get_db)):
    return db.query(Facility).all()

@router.post("/", response_model=FacilitySchema, dependencies=[Depends(RequirePermission("manage_users"))]) # Use manage_users or manage_settings for admin-level
def create_facility(facility: FacilityCreate, db: Session = Depends(get_db)):
    db_facility = Facility(**facility.dict())
    db.add(db_facility)
    db.commit()
    db.refresh(db_facility)
    return db_facility

@router.get("/{facility_id}", response_model=FacilitySchema)
def get_facility(facility_id: int, db: Session = Depends(get_db)):
    db_facility = db.query(Facility).filter(Facility.id == facility_id).first()
    if not db_facility:
        raise HTTPException(status_code=404, detail="Facility not found")
    return db_facility

@router.put("/{facility_id}", response_model=FacilitySchema, dependencies=[Depends(RequirePermission("manage_users"))])
def update_facility(facility_id: int, facility_update: FacilityCreate, db: Session = Depends(get_db)):
    db_facility = db.query(Facility).filter(Facility.id == facility_id).first()
    if not db_facility:
        raise HTTPException(status_code=404, detail="Facility not found")
    
    for var, value in vars(facility_update).items():
        setattr(db_facility, var, value)
        
    db.commit()
    db.refresh(db_facility)
    return db_facility
