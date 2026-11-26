from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional
import os
from pathlib import Path
import uuid
from app.core.database import get_db
from app.models.document import Document
from app.models.encounter import Encounter
from app.models.patient import Patient
from app.schemas.document import Document as DocumentSchema
from app.api.deps import RequirePermission, get_current_user
from app.models.user import User

router = APIRouter()

UPLOAD_DIR = "uploads"

if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)


def document_path(file_path: str) -> Path:
    root = Path(UPLOAD_DIR).resolve()
    path = Path(file_path).resolve()
    if path == root or not path.is_relative_to(root):
        raise HTTPException(status_code=404, detail="File not found on server")
    return path

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
    if not db.get(Patient, patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")
    if encounter_id is not None:
        encounter = db.get(Encounter, encounter_id)
        if not encounter or encounter.patient_id != patient_id:
            raise HTTPException(status_code=422, detail="Document encounter does not belong to this patient")

    ext = os.path.splitext(file.filename or "")[1].lower()
    formats = {
        ".jpg": ("image/jpeg", b"\xff\xd8\xff"),
        ".jpeg": ("image/jpeg", b"\xff\xd8\xff"),
        ".png": ("image/png", b"\x89PNG\r\n\x1a\n"),
        ".pdf": ("application/pdf", b"%PDF-"),
    }
    if ext not in formats:
        raise HTTPException(status_code=400, detail="Invalid file extension. Allowed: .jpg, .jpeg, .png, .pdf")

    mime_type, signature = formats[ext]
    if file.content_type != mime_type:
        raise HTTPException(status_code=400, detail="Invalid MIME type")

    content = await file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 5MB")
    if not content.startswith(signature):
        raise HTTPException(status_code=400, detail="File content does not match its type")

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
    path = document_path(db_doc.file_path)
    if path.is_file():
        path.unlink()

    db.delete(db_doc)
    db.commit()
    return {"detail": "Document deleted successfully"}

@router.get("/documents/{document_id}/download", dependencies=[Depends(RequirePermission("view_patients"))])
def download_document(document_id: int, db: Session = Depends(get_db)):
    db_doc = db.query(Document).filter(Document.id == document_id).first()
    if not db_doc:
        raise HTTPException(status_code=404, detail="Document not found")

    path = document_path(db_doc.file_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File not found on server")

    return FileResponse(path=path, filename=path.name)
