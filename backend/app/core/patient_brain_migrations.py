"""Idempotent upgrade for the Patient Brain and PG Assistant schema."""
from sqlalchemy import inspect
from app.models.patient_brain import (
    PatientProblem,
    ClinicalEvent,
    ClinicalDecision,
    OpenLoop,
    MedicationEvent,
    PatientFlag,
    BrainSnapshot,
    AIInteraction,
    BrainCorrection,
    ConversationState,
)


def migrate_patient_brain(conn):
    """Ensure all Patient Brain tables exist."""
    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())

    tables = [
        PatientProblem.__table__,
        ClinicalEvent.__table__,
        ClinicalDecision.__table__,
        OpenLoop.__table__,
        MedicationEvent.__table__,
        PatientFlag.__table__,
        BrainSnapshot.__table__,
        AIInteraction.__table__,
        BrainCorrection.__table__,
        ConversationState.__table__,
    ]

    for table in tables:
        if table.name not in existing_tables:
            table.create(bind=conn, checkfirst=True)
