"""Idempotent upgrade for the encounter revision and amendment schema."""

from sqlalchemy import inspect, text
from app.models.encounter import EncounterAmendment


def migrate_encounter_lifecycle(conn):
    inspector = inspect(conn)
    if not inspector.has_table("encounters"):
        return

    columns = {column["name"] for column in inspector.get_columns("encounters")}
    if "version" not in columns:
        conn.execute(text("ALTER TABLE encounters ADD COLUMN version INTEGER NOT NULL DEFAULT 1"))
    if "signed_at" not in columns:
        conn.execute(text("ALTER TABLE encounters ADD COLUMN signed_at TIMESTAMP"))
    if "signed_by_id" not in columns:
        conn.execute(text("ALTER TABLE encounters ADD COLUMN signed_by_id INTEGER"))
    if "draft_orders" not in columns:
        conn.execute(text("ALTER TABLE encounters ADD COLUMN draft_orders JSON"))
    EncounterAmendment.__table__.create(bind=conn, checkfirst=True)
