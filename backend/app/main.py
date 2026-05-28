from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import auth, users, patients, appointments, clinical, billing, settings, encounters, allergies, medical_problems, medications, prescriptions, immunizations, lab_results, insurance, facilities, documents, messages

app = FastAPI(title="EMR Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Update for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(patients.router, prefix="/api/patients", tags=["patients"])
app.include_router(appointments.router, prefix="/api/appointments", tags=["appointments"])
app.include_router(clinical.router, prefix="/api/clinical", tags=["clinical"])
app.include_router(billing.router, prefix="/api/billing", tags=["billing"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
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

@app.on_event("startup")
def on_startup():
    try:
        import seed
        seed.seed_db()
    except Exception as e:
        print(f"Error seeding database: {e}")

@app.get("/")
def read_root():
    return {"message": "Welcome to EMR API"}
