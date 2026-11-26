"""
Temporary Media endpoint.
Serves PDFs via signed JWT tokens that expire after 5 minutes.
"""
import os
import logging
from pathlib import Path
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
import jwt
from jwt import InvalidTokenError as JWTError

logger = logging.getLogger(__name__)

router = APIRouter()

from app.core.security import SECRET_KEY, ALGORITHM
MEDIA_EXPIRY_MINUTES = 5
TEMP_PDF_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "services", "..", "..", "temp_pdfs")


def create_media_token(filename: str) -> str:
    """Create a signed JWT token for temporary file access (5-minute expiry)."""
    expire = datetime.utcnow() + timedelta(minutes=MEDIA_EXPIRY_MINUTES)
    payload = {"filename": filename, "exp": expire, "token_use": "media"}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_media_url(filename: str) -> str:
    """Generate a full public URL for a temporary PDF file."""
    token = create_media_token(filename)
    public_url = os.environ.get("BACKEND_PUBLIC_URL", "").rstrip("/")
    if not public_url:
        public_url = "http://localhost:8000"
    return f"{public_url}/api/media/{token}"


@router.get("/{token}")
def serve_media(token: str):
    """Serve a temporary file if the token is valid and not expired."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"require": ["exp"]})
        filename = payload.get("filename")
        if not isinstance(filename, str) or not filename or payload.get("token_use") != "media":
            raise HTTPException(status_code=400, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=403, detail="Link has expired or is invalid")

    # Resolve the temp PDF directory safely
    temp_dir = Path(TEMP_PDF_DIR).resolve()
    filepath = (temp_dir / filename).resolve()

    # Prevent path traversal
    if not filepath.is_relative_to(temp_dir):
        raise HTTPException(status_code=403, detail="Access denied")

    if not os.path.isfile(filepath):
        raise HTTPException(status_code=404, detail="File not found or has been cleaned up")

    return FileResponse(
        filepath,
        media_type="application/pdf",
        filename=filename,
    )
