from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
import os
import uuid
from app.core.database import get_db
from app.models.document import Document
from app.schemas.document import Document as DocumentSchema
from app.api.deps import RequirePermission, get_current_user
from app.models.user import User

router = APIRouter()

UPLOAD_DIR = "uploads"

if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

@router.get("/patients/{patient_id}/documents", response_model=List[DocumentSchema], dependencies=[Depends(RequirePermission("view_patients"))])
def get_documents(patient_id: int, db: Session = Depends(get_db)):
    return db.query(Document).filter(Document.patient_id == patient_id).all()

@router.post("/patients/{patient_id}/documents", response_model=DocumentSchema, dependencies=[Depends(RequirePermission("manage_patients"))])
async def upload_document(
    patient_id: int, 
    type: str = Form(...),
    title: str = Form(...),
    notes: Optional[str] = Form(None),
    encounter_id: Optional[int] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Save file
    ext = os.path.splitext(file.filename)[1].lower()
    allowed_extensions = {".jpg", ".jpeg", ".png", ".pdf"}
    if ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail="Invalid file extension. Allowed: .jpg, .jpeg, .png, .pdf")

    if file.content_type not in {"image/jpeg", "image/png", "application/pdf"}:
        raise HTTPException(status_code=400, detail="Invalid MIME type")

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 5MB")

    safe_filename = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(UPLOAD_DIR, f"{patient_id}_{safe_filename}")
    with open(file_path, "wb") as f:
        f.write(content)
        
    db_doc = Document(
        patient_id=patient_id,
        encounter_id=encounter_id,
        type=type,
        title=title,
        file_path=file_path,
        uploaded_by=current_user.id,
        notes=notes
    )
    db.add(db_doc)
    db.commit()
    db.refresh(db_doc)
    return db_doc

@router.delete("/documents/{document_id}", dependencies=[Depends(RequirePermission("manage_patients"))])
def delete_document(document_id: int, db: Session = Depends(get_db)):
    db_doc = db.query(Document).filter(Document.id == document_id).first()
    if not db_doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    # Optional: Delete physical file
    if os.path.exists(db_doc.file_path):
        os.remove(db_doc.file_path)
        
    db.delete(db_doc)
    db.commit()
    return {"detail": "Document deleted successfully"}
