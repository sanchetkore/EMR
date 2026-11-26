from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.lab_result import LabResult


# Older manual results can have an order date without a completion timestamp.
manual_report_date = func.coalesce(LabResult.result_date, LabResult.ordered_date)


def completed_lab_results(db: Session, patient_id: int):
    return db.query(LabResult).filter(
        LabResult.patient_id == patient_id,
        LabResult.status == "Completed",
        LabResult.result_value.isnot(None),
    ).order_by(manual_report_date.desc().nulls_last(), LabResult.id.desc())


def report_recency(value: datetime | None) -> datetime:
    if value is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    # EMR and legacy LIS timestamps without an offset are stored in UTC.
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
