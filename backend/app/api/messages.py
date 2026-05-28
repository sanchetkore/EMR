from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.database import get_db
from app.models.message import Message
from app.schemas.message import Message as MessageSchema, MessageCreate
from app.api.deps import RequirePermission, get_current_user
from app.models.user import User

router = APIRouter()

@router.get("/inbox", response_model=List[MessageSchema])
def get_inbox(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(Message).filter(Message.receiver_id == current_user.id).order_by(Message.created_at.desc()).all()

@router.get("/sent", response_model=List[MessageSchema])
def get_sent(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(Message).filter(Message.sender_id == current_user.id).order_by(Message.created_at.desc()).all()

@router.post("/", response_model=MessageSchema)
def create_message(message: MessageCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_message = Message(**message.dict(), sender_id=current_user.id)
    db.add(db_message)
    db.commit()
    db.refresh(db_message)
    return db_message

@router.put("/{message_id}/read", response_model=MessageSchema)
def mark_read(message_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_message = db.query(Message).filter(Message.id == message_id, Message.receiver_id == current_user.id).first()
    if not db_message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    db_message.status = "Read"
    db.commit()
    db.refresh(db_message)
    return db_message
