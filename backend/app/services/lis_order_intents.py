"""Claim and deliver persisted visit lab requests with stable LIS identity."""

from datetime import datetime, timedelta
import logging

from fastapi import HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.visit_lab_intent import VisitLabOrderIntent

logger = logging.getLogger(__name__)


def _submit_to_lis(intent: VisitLabOrderIntent, db: Session):
    from app.api.lis_integration import LISOrderRequest, create_lis_order

    requester = db.get(User, intent.requested_by_id)
    if requester is None:
        raise RuntimeError("Requesting clinician no longer exists")
    return create_lis_order(
        LISOrderRequest(
            patient_id=intent.patient_id,
            test_codes=intent.test_codes,
            package_codes=intent.package_codes,
            source_id=intent.source_id,
            notes=intent.notes,
        ),
        db=db,
        current_user=requester,
        expected_connection_id=intent.connection_id,
    )


def process_lab_intent(db: Session, intent_id: int, *, force: bool = False, submit_order=None, now=None):
    now = now or datetime.utcnow()
    due = or_(VisitLabOrderIntent.retry_after.is_(None), VisitLabOrderIntent.retry_after <= now)
    available = or_(
        and_(VisitLabOrderIntent.status.in_(["PENDING", "FAILED"]),
             or_(due, force)),
        and_(VisitLabOrderIntent.status == "PROCESSING",
             VisitLabOrderIntent.lease_expires_at <= now),
    )
    claimed = db.query(VisitLabOrderIntent).filter(
        VisitLabOrderIntent.id == intent_id, available,
    ).update({
        VisitLabOrderIntent.status: "PROCESSING",
        VisitLabOrderIntent.lease_expires_at: now + timedelta(minutes=2),
        VisitLabOrderIntent.retry_after: None,
        VisitLabOrderIntent.attempt_count: VisitLabOrderIntent.attempt_count + 1,
    }, synchronize_session=False)
    db.commit()
    intent = db.get(VisitLabOrderIntent, intent_id)
    if not intent:
        return None
    if claimed != 1:
        return intent

    try:
        response = (submit_order or _submit_to_lis)(intent, db)
        db.refresh(intent)
        intent.status = "ACCEPTED"
        intent.remote_order_id = str(response.get("id") or "") or None
        intent.accession_number = response.get("accessionNumber")
        intent.last_error = None
        intent.lease_expires_at = None
        db.commit()
    except Exception as error:
        db.rollback()
        intent = db.get(VisitLabOrderIntent, intent_id)
        if isinstance(error, HTTPException):
            message = str(error.detail)
        else:
            message = "Laboratory delivery failed; retry is scheduled."
            logger.exception("LIS order delivery failed for intent %s", intent_id)
        intent.status = "FAILED"
        intent.last_error = message[:500]
        intent.lease_expires_at = None
        delay_seconds = min(60 * (2 ** min(intent.attempt_count - 1, 6)), 3600)
        intent.retry_after = datetime.utcnow() + timedelta(seconds=delay_seconds)
        db.commit()
    db.refresh(intent)
    return intent
