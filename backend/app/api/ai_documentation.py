import os
from fastapi import APIRouter, Depends, HTTPException, Request
from app.api.deps import RequirePermission
from app.core.limiter import limiter
from app.schemas.ai_documentation import DocumentationInput, DocumentationDraft
from app.services.ai_documentation import prepare_documentation, DocumentationInputError

router = APIRouter()


@router.get("/status", dependencies=[Depends(RequirePermission("manage_clinical"))])
def documentation_status():
    return {"configured": bool(os.getenv("OPEN_AI_KEY") or os.getenv("OPENAI_API_KEY")),
            "capabilities": ["documentation_draft", "documentation_checklist"]}


@router.post("/documentation", response_model=DocumentationDraft,
             dependencies=[Depends(RequirePermission("manage_clinical"))])
@limiter.limit("10/minute")
def draft_documentation(request: Request, payload: DocumentationInput):
    try:
        return prepare_documentation(payload)
    except DocumentationInputError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    except Exception:
        raise HTTPException(status_code=503, detail="AI documentation is unavailable. Your consultation remains editable; retry or write the note directly.") from None
