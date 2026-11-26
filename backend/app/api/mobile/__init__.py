from fastapi import APIRouter
from app.api.mobile import auth, doctors, appointments, medical_history, labs, payments, notifications

mobile_router = APIRouter(prefix="/mobile/v1")

mobile_router.include_router(auth.router)
mobile_router.include_router(doctors.router)
mobile_router.include_router(appointments.router)
mobile_router.include_router(medical_history.router)
mobile_router.include_router(labs.router)
mobile_router.include_router(payments.router)
mobile_router.include_router(notifications.router)
