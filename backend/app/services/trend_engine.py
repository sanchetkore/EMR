"""Deterministic trend analysis engine for laboratory tests and vitals.
No AI dependencies - uses pure mathematical and rule-based calculations.
"""
import re
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.models.lab_result import LabResult
from app.models.encounter import Encounter, PatientVital, VitalConfiguration
from app.schemas.patient_brain import MetricTrend, TrendPoint


def _extract_numeric(val: Any) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    val_str = str(val).strip()
    match = re.search(r"[-+]?\d*\.?\d+", val_str)
    if match:
        try:
            return float(match.group(0))
        except ValueError:
            return None
    return None


def calculate_lab_trends(db: Session, patient_id: int) -> List[MetricTrend]:
    """Calculate deterministic trends for all completed lab results for a patient."""
    labs = (
        db.query(LabResult)
        .filter(LabResult.patient_id == patient_id, LabResult.status == "Completed")
        .order_by(LabResult.result_date.asc(), LabResult.id.asc())
        .all()
    )

    # Group by normalized test name
    grouped: Dict[str, List[LabResult]] = {}
    for lab in labs:
        name = (lab.test_name or "Unknown").strip()
        grouped.setdefault(name, []).append(lab)

    trends: List[MetricTrend] = []
    for test_name, results in grouped.items():
        if not results:
            continue

        history_points: List[TrendPoint] = []
        for r in results:
            num = _extract_numeric(r.result_value)
            d_str = r.result_date.strftime("%Y-%m-%d") if r.result_date else (r.ordered_date.strftime("%Y-%m-%d") if r.ordered_date else "")
            history_points.append(
                TrendPoint(
                    date=d_str,
                    value=num if num is not None else 0.0,
                    display_value=str(r.result_value or ""),
                    source_id=r.id,
                )
            )

        latest_record = results[-1]
        latest_val = _extract_numeric(latest_record.result_value)
        latest_date_str = latest_record.result_date.strftime("%Y-%m-%d") if latest_record.result_date else None

        previous_record = results[-2] if len(results) >= 2 else None
        previous_val = _extract_numeric(previous_record.result_value) if previous_record else None
        previous_date_str = (
            previous_record.result_date.strftime("%Y-%m-%d")
            if (previous_record and previous_record.result_date)
            else None
        )

        delta = None
        pct_change = None
        direction = "stable"

        if latest_val is not None and previous_val is not None:
            delta = round(latest_val - previous_val, 2)
            if previous_val != 0:
                pct_change = round(((latest_val - previous_val) / abs(previous_val)) * 100, 1)

            if delta > 0.01:
                direction = "increased"
            elif delta < -0.01:
                direction = "decreased"
            else:
                direction = "stable"

        # Consecutive direction count
        consecutive_count = 0
        if len(history_points) >= 2:
            num_history = [p.value for p in history_points if p.value is not None]
            if len(num_history) >= 2:
                last_diff = num_history[-1] - num_history[-2]
                target_dir = 1 if last_diff > 0.01 else (-1 if last_diff < -0.01 else 0)
                if target_dir != 0:
                    for i in range(len(num_history) - 1, 0, -1):
                        diff = num_history[i] - num_history[i - 1]
                        cur_dir = 1 if diff > 0.01 else (-1 if diff < -0.01 else 0)
                        if cur_dir == target_dir:
                            consecutive_count += 1
                        else:
                            break

        # Clinical status
        clinical_status = "normal"
        ref_range = latest_record.reference_range
        if ref_range and latest_val is not None:
            # Parse simple ranges like "70 - 110", "4.0-6.0", "< 5.7"
            range_match = re.search(r"(\d+\.?\d*)\s*[-–]\s*(\d+\.?\d*)", ref_range)
            less_than_match = re.search(r"<\s*(\d+\.?\d*)", ref_range)
            greater_than_match = re.search(r">\s*(\d+\.?\d*)", ref_range)

            if range_match:
                low, high = float(range_match.group(1)), float(range_match.group(2))
                if latest_val < low:
                    clinical_status = "abnormal_low"
                elif latest_val > high:
                    clinical_status = "abnormal_high"
            elif less_than_match:
                high = float(less_than_match.group(1))
                if latest_val > high:
                    clinical_status = "abnormal_high"
            elif greater_than_match:
                low = float(greater_than_match.group(1))
                if latest_val < low:
                    clinical_status = "abnormal_low"

        trends.append(
            MetricTrend(
                metric_name=test_name,
                category="lab",
                unit=latest_record.unit,
                reference_range=latest_record.reference_range,
                latest_value=latest_val,
                latest_display=str(latest_record.result_value or "Pending"),
                latest_date=latest_date_str,
                previous_value=previous_val,
                previous_display=str(previous_record.result_value) if previous_record else None,
                previous_date=previous_date_str,
                delta=delta,
                percent_change=pct_change,
                direction=direction,
                consecutive_direction_count=consecutive_count,
                clinical_status=clinical_status,
                history=history_points,
            )
        )

    return trends


def calculate_vital_trends(db: Session, patient_id: int) -> List[MetricTrend]:
    """Calculate deterministic longitudinal vital trends across encounters."""
    encounters = (
        db.query(Encounter)
        .filter(Encounter.patient_id == patient_id)
        .order_by(Encounter.encounter_date.asc(), Encounter.id.asc())
        .all()
    )

    vital_configs = {vc.id: vc.name.lower() for vc in db.query(VitalConfiguration).all()}

    # Collect vitals per config name
    by_name: Dict[str, List[Dict[str, Any]]] = {}

    for enc in encounters:
        d_str = enc.encounter_date.strftime("%Y-%m-%d") if enc.encounter_date else ""
        for pv in enc.vitals:
            name = vital_configs.get(pv.vital_config_id, "vital")
            if pv.value:
                by_name.setdefault(name, []).append({
                    "date": d_str,
                    "raw": pv.value.strip(),
                    "source_id": enc.id
                })

    trends: List[MetricTrend] = []

    for name, entries in by_name.items():
        if not entries:
            continue

        # Handle BP specially if format "120/80"
        if "bp" in name or "blood pressure" in name:
            systolic_points: List[TrendPoint] = []
            for e in entries:
                parts = e["raw"].split("/")
                sys_val = _extract_numeric(parts[0]) if len(parts) > 0 else None
                if sys_val is not None:
                    systolic_points.append(
                        TrendPoint(date=e["date"], value=sys_val, display_value=e["raw"], source_id=e["source_id"])
                    )

            if systolic_points:
                latest_p = systolic_points[-1]
                prev_p = systolic_points[-2] if len(systolic_points) >= 2 else None
                delta = round(latest_p.value - prev_p.value, 1) if prev_p else None
                direction = "increased" if delta and delta > 2 else ("decreased" if delta and delta < -2 else "stable")
                status = "abnormal_high" if latest_p.value >= 140 else "normal"

                trends.append(
                    MetricTrend(
                        metric_name="Blood Pressure",
                        category="vital",
                        unit="mmHg",
                        reference_range="90-120/60-80",
                        latest_value=latest_p.value,
                        latest_display=latest_p.display_value,
                        latest_date=latest_p.date,
                        previous_value=prev_p.value if prev_p else None,
                        previous_display=prev_p.display_value if prev_p else None,
                        previous_date=prev_p.date if prev_p else None,
                        delta=delta,
                        direction=direction,
                        clinical_status=status,
                        history=systolic_points,
                    )
                )
        else:
            # Generic numeric vital (Weight, Pulse, Sugar, etc.)
            points: List[TrendPoint] = []
            for e in entries:
                val = _extract_numeric(e["raw"])
                if val is not None:
                    points.append(
                        TrendPoint(date=e["date"], value=val, display_value=e["raw"], source_id=e["source_id"])
                    )

            if points:
                latest_p = points[-1]
                prev_p = points[-2] if len(points) >= 2 else None
                delta = round(latest_p.value - prev_p.value, 1) if prev_p else None
                pct = round(((latest_p.value - prev_p.value) / abs(prev_p.value)) * 100, 1) if (prev_p and prev_p.value) else None
                direction = "increased" if delta and delta > 0.1 else ("decreased" if delta and delta < -0.1 else "stable")

                trends.append(
                    MetricTrend(
                        metric_name=name.capitalize(),
                        category="vital",
                        latest_value=latest_p.value,
                        latest_display=latest_p.display_value,
                        latest_date=latest_p.date,
                        previous_value=prev_p.value if prev_p else None,
                        previous_display=prev_p.display_value if prev_p else None,
                        previous_date=prev_p.date if prev_p else None,
                        delta=delta,
                        percent_change=pct,
                        direction=direction,
                        clinical_status="normal",
                        history=points,
                    )
                )

    return trends
