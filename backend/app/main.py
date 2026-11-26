from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from app.core.limiter import limiter
from app.api import auth, users, patients, appointments, clinical, billing, settings, encounters, allergies, medical_problems, medications, prescriptions, immunizations, lab_results, insurance, facilities, documents, messages, visits, drugs, queue, clinic, pharmacy, dashboard, ws, templates, media, lis_integration
import os
import logging
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="EMR Backend")
from app.core.request_limits import RequestBodyLimitMiddleware
app.add_middleware(RequestBodyLimitMiddleware)

from app.api import ai_documentation, patient_brain
app.include_router(ai_documentation.router, prefix="/api/ai", tags=["ai-documentation"])
app.include_router(patient_brain.router, prefix="/api", tags=["patient-brain"])

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

class RedactMediaAccessPath(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) == 5 and isinstance(args[2], str) and args[2].startswith("/api/media/"):
            record.args = (*args[:2], "/api/media/[redacted]", *args[3:])
        return True


logging.getLogger("uvicorn.access").addFilter(RedactMediaAccessPath())

cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    response.headers["Referrer-Policy"] = "no-referrer"
    if (request.headers.get("authorization")
            or request.url.path.startswith(("/api/mobile/", "/api/auth/", "/api/media/"))):
        response.headers["Cache-Control"] = "no-store"
    return response

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(patients.router, prefix="/api/patients", tags=["patients"])
app.include_router(appointments.router, prefix="/api/appointments", tags=["appointments"])
app.include_router(clinical.router, prefix="/api/clinical", tags=["clinical"])
app.include_router(billing.router, prefix="/api/billing", tags=["billing"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(lis_integration.router, prefix="/api/integrations/lis", tags=["lis-integration"])
app.include_router(encounters.router, prefix="/api/encounters", tags=["encounters"])
app.include_router(allergies.router, prefix="/api", tags=["allergies"])
app.include_router(medical_problems.router, prefix="/api", tags=["medical_problems"])
app.include_router(medications.router, prefix="/api", tags=["medications"])
app.include_router(prescriptions.router, prefix="/api/prescriptions", tags=["prescriptions"])
app.include_router(immunizations.router, prefix="/api", tags=["immunizations"])
app.include_router(lab_results.router, prefix="/api", tags=["lab_results"])
app.include_router(insurance.router, prefix="/api", tags=["insurance"])
app.include_router(facilities.router, prefix="/api/facilities", tags=["facilities"])
app.include_router(documents.router, prefix="/api", tags=["documents"])
app.include_router(messages.router, prefix="/api/messages", tags=["messages"])
app.include_router(visits.router, prefix="/api/visits", tags=["visits"])
app.include_router(drugs.router, prefix="/api/drugs", tags=["drugs"])
app.include_router(queue.router, prefix="/api/queue", tags=["queue"])
app.include_router(clinic.router, prefix="/api/clinic", tags=["clinic"])
app.include_router(pharmacy.router, prefix="/api/pharmacy", tags=["pharmacy"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(ws.router, prefix="/api/ws", tags=["websocket"])
app.include_router(templates.router, prefix="/api/v1/templates", tags=["templates"])
app.include_router(media.router, prefix="/api/media", tags=["media"])
from app.api.mobile import mobile_router
app.include_router(mobile_router, prefix="/api", tags=["mobile"])
if not os.path.exists("uploads"):
    os.makedirs("uploads")
if not os.path.exists("public_assets"):
    os.makedirs("public_assets")
app.mount("/api/public_assets", StaticFiles(directory="public_assets", follow_symlink=False), name="public_assets")

@app.on_event("startup")
def on_startup():
    import seed
    seed.seed_db()

@app.get("/")
def read_root():
    return {"message": "Welcome to EMR API"}
