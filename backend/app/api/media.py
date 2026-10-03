"""
Temporary Media endpoint.
Serves PDFs via signed JWT tokens that expire after 5 minutes.
"""
import os
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from jose import jwt, JWTError

logger = logging.getLogger(__name__)

router = APIRouter()

SECRET_KEY = os.environ.get("SECRET_KEY", "super_secret_key_change_in_production_v2")
ALGORITHM = "HS256"
MEDIA_EXPIRY_MINUTES = 5
TEMP_PDF_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "services", "..", "..", "temp_pdfs")


def create_media_token(filename: str) -> str:
    """Create a signed JWT token for temporary file access (5-minute expiry)."""
    expire = datetime.utcnow() + timedelta(minutes=MEDIA_EXPIRY_MINUTES)
    payload = {"filename": filename, "exp": expire}
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
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        filename = payload.get("filename")
        if not filename:
            raise HTTPException(status_code=400, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=403, detail="Link has expired or is invalid")

    # Resolve the temp PDF directory safely
    temp_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "temp_pdfs"))
    filepath = os.path.normpath(os.path.join(temp_dir, filename))

    # Prevent path traversal
    if not filepath.startswith(temp_dir):
        raise HTTPException(status_code=403, detail="Access denied")

    if not os.path.isfile(filepath):
        raise HTTPException(status_code=404, detail="File not found or has been cleaned up")

    return FileResponse(
        filepath,
        media_type="application/pdf",
        filename=filename,
    )
