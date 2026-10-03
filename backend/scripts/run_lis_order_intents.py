"""Run with `python -m scripts.run_lis_order_intents` in the EMR backend image."""

import logging
import time
from datetime import datetime
from sqlalchemy import and_, or_

import app.models  # Register all tables before opening sessions.
from app.core.database import SessionLocal
from app.models.visit_lab_intent import VisitLabOrderIntent
from app.services.lis_order_intents import process_lab_intent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_once():
    with SessionLocal() as db:
        now = datetime.utcnow()
        ids = [row[0] for row in db.query(VisitLabOrderIntent.id).filter(
            or_(
                and_(VisitLabOrderIntent.status.in_(["PENDING", "FAILED"]),
                     or_(VisitLabOrderIntent.retry_after.is_(None), VisitLabOrderIntent.retry_after <= now)),
                and_(VisitLabOrderIntent.status == "PROCESSING", VisitLabOrderIntent.lease_expires_at <= now),
            ),
        ).order_by(VisitLabOrderIntent.created_at.asc()).limit(20).all()]
        for intent_id in ids:
            process_lab_intent(db, intent_id)


if __name__ == "__main__":
    while True:
        try:
            run_once()
        except Exception:
            logger.exception("Lab intent scan failed; retrying")
        time.sleep(15)
