"""Comprehensive tests for Patient Brain & PG Assistant implementation.
Verifies all 12 stages: deterministic trends, clinical events, open loop auto-matching,
'why?' clinical memory, prepare patient, since last visit, attention engine,
PG assistant router/context, and doctor corrections.
"""
import os
import unittest
from datetime import datetime, date, timedelta, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure test DB environment
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.core.database import Base
from app.models.user import User, Role
from app.models.patient import Patient, Appointment
from app.models.encounter import Encounter, PatientVital, VitalConfiguration, VisitDiagnosis, VisitTreatment
from app.models.lab_result import LabResult, LabCatalog
from app.models.medication import Medication
from app.models.allergy import Allergy
from app.models.medical_problem import MedicalProblem
from app.models.patient_brain import (
    PatientProblem,
    ClinicalEvent,
    ClinicalDecision,
    OpenLoop,
    MedicationEvent,
    BrainSnapshot,
    BrainCorrection,
    AIInteraction,
    ConversationState,
)

from app.services.trend_engine import calculate_lab_trends, calculate_vital_trends
from app.services.clinical_event_engine import (
    record_clinical_event,
    get_patient_timeline,
    get_problem_timeline,
    sync_historical_records_to_events,
)
from app.services.open_loops_engine import (
    create_open_loop,
    get_patient_open_loops,
    match_open_loops,
    close_open_loop,
)
from app.services.why_memory_service import (
    record_medication_event,
    record_clinical_decision,
    get_medication_intelligence,
)
from app.services.since_last_visit_service import get_changes_since_last_visit
from app.services.attention_engine import get_patient_attention_items, get_clinic_attention_queue
from app.services.prepare_patient_service import get_prepared_patient_brief
from app.services.patient_brain_service import get_or_build_patient_brain, record_brain_correction
from app.services.pg_assistant_service import query_pg_assistant, route_intent
from app.services.plan_structuring_service import (
    extract_plan_actions_deterministic,
    commit_plan_actions,
)


class PatientBrainTestSuite(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.db = self.Session()

        # Seed clinician user
        self.doctor = User(
            id=1,
            username="dr_sharma",
            email="sharma@skfb.com",
            hashed_password="hash",
            is_active=1,
        )
        self.db.add(self.doctor)

        # Seed patient (Ramesh Patil, 58M)
        self.patient = Patient(
            id=1842,
            first_name="Ramesh",
            last_name="Patil",
            dob=date(1968, 4, 15),
            gender="Male",
            opd_number="OPD-1842",
            contact_number="9876543210",
            blood_group="B+",
            is_active=1,
        )
        self.db.add(self.patient)

        # Seed vital configurations
        self.vc_bp = VitalConfiguration(id=1, name="BP", data_type="string")
        self.vc_wt = VitalConfiguration(id=2, name="Weight", data_type="numeric")
        self.db.add_all([self.vc_bp, self.vc_wt])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    # ---------------------------------------------------------------------
    # Stage 1 & 3: Deterministic Trend Engine
    # ---------------------------------------------------------------------
    def test_deterministic_lab_trends(self):
        # Add 3 historical HbA1c lab tests: 7.4 -> 7.8 -> 8.6
        lab1 = LabResult(
            patient_id=self.patient.id,
            test_name="HbA1c",
            result_value="7.4",
            unit="%",
            reference_range="4.0 - 5.6",
            status="Completed",
            result_date=datetime(2025, 1, 12),
        )
        lab2 = LabResult(
            patient_id=self.patient.id,
            test_name="HbA1c",
            result_value="7.8",
            unit="%",
            reference_range="4.0 - 5.6",
            status="Completed",
            result_date=datetime(2025, 4, 12),
        )
        lab3 = LabResult(
            patient_id=self.patient.id,
            test_name="HbA1c",
            result_value="8.6",
            unit="%",
            reference_range="4.0 - 5.6",
            status="Completed",
            result_date=datetime(2025, 7, 16),
        )
        self.db.add_all([lab1, lab2, lab3])
        self.db.commit()

        trends = calculate_lab_trends(self.db, self.patient.id)
        self.assertEqual(len(trends), 1)
        hba1c_trend = trends[0]

        self.assertEqual(hba1c_trend.metric_name, "HbA1c")
        self.assertEqual(hba1c_trend.latest_value, 8.6)
        self.assertEqual(hba1c_trend.previous_value, 7.8)
        self.assertEqual(hba1c_trend.delta, 0.8)
        self.assertEqual(hba1c_trend.direction, "increased")
        self.assertEqual(hba1c_trend.consecutive_direction_count, 2)
        self.assertEqual(hba1c_trend.clinical_status, "abnormal_high")
        self.assertEqual(len(hba1c_trend.history), 3)

    def test_deterministic_vital_trends(self):
        # Two visits with BP 144/88 and 152/94
        enc1 = Encounter(
            patient_id=self.patient.id,
            doctor_id=self.doctor.id,
            encounter_date=datetime(2025, 4, 12),
            status="Completed",
        )
        enc2 = Encounter(
            patient_id=self.patient.id,
            doctor_id=self.doctor.id,
            encounter_date=datetime(2025, 7, 16),
            status="Completed",
        )
        self.db.add_all([enc1, enc2])
        self.db.commit()

        v1 = PatientVital(encounter_id=enc1.id, vital_config_id=self.vc_bp.id, value="144/88")
        v2 = PatientVital(encounter_id=enc2.id, vital_config_id=self.vc_bp.id, value="152/94")
        self.db.add_all([v1, v2])
        self.db.commit()

        vital_trends = calculate_vital_trends(self.db, self.patient.id)
        bp_trend = next((vt for vt in vital_trends if "blood pressure" in vt.metric_name.lower()), None)
        self.assertIsNotNone(bp_trend)
        self.assertEqual(bp_trend.latest_display, "152/94")
        self.assertEqual(bp_trend.previous_display, "144/88")
        self.assertEqual(bp_trend.delta, 8.0)
        self.assertEqual(bp_trend.direction, "increased")

    # ---------------------------------------------------------------------
    # Stage 2: Clinical Event Engine & Timeline
    # ---------------------------------------------------------------------
    def test_clinical_events_and_timelines(self):
        # Seed problem and visit
        prob = MedicalProblem(
            patient_id=self.patient.id,
            title="Type 2 Diabetes Mellitus",
            status="Active",
            onset_date=date(2021, 6, 1),
        )
        self.db.add(prob)
        self.db.commit()

        events = get_patient_timeline(self.db, self.patient.id)
        self.assertTrue(len(events) >= 1)
        self.assertTrue(any("Diabetes" in e.title for e in events))

        # Problem-specific timeline
        dm_timeline = get_problem_timeline(self.db, self.patient.id, "Diabetes")
        self.assertTrue(len(dm_timeline) >= 1)
        self.assertTrue(all("diabetes" in (e.title + (e.summary or "")).lower() for e in dm_timeline))

    # ---------------------------------------------------------------------
    # Stage 5 & 7: Open Loops Engine & Auto-Matching
    # ---------------------------------------------------------------------
    def test_open_loops_lifecycle_and_auto_matching(self):
        # Doctor sets loop: "Repeat HbA1c" expected in 3 months
        future_date = date.today() + timedelta(days=90)
        loop1 = create_open_loop(
            db=self.db,
            patient_id=self.patient.id,
            loop_type="lab",
            description="Repeat HbA1c",
            target_code="HBA1C",
            expected_date=future_date,
        )
        self.assertEqual(loop1.status, "pending")

        # Overdue loop: "Repeat Creatinine" expected 10 days ago
        past_date = date.today() - timedelta(days=10)
        loop2 = create_open_loop(
            db=self.db,
            patient_id=self.patient.id,
            loop_type="lab",
            description="Repeat Creatinine",
            target_code="CREATININE",
            expected_date=past_date,
        )

        open_loops = get_patient_open_loops(self.db, self.patient.id)
        overdue_item = next((l for l in open_loops if l.id == loop2.id), None)
        self.assertIsNotNone(overdue_item)
        self.assertTrue(overdue_item.is_overdue)
        self.assertEqual(overdue_item.days_overdue, 10)

        # New result arrives: Creatinine 1.3 mg/dL -> trigger match_open_loops
        matched = match_open_loops(
            db=self.db,
            patient_id=self.patient.id,
            event_type="lab",
            test_name_or_code="Serum Creatinine",
            result_id=999,
        )
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0].id, loop2.id)
        self.assertEqual(matched[0].status, "completed")
        self.assertEqual(matched[0].result_id, 999)
        self.assertIsNotNone(matched[0].completed_at)

    # ---------------------------------------------------------------------
    # Stage 6: "Why?" Clinical Memory & Prescription Intelligence
    # ---------------------------------------------------------------------
    def test_why_clinical_memory_and_prescription_intelligence(self):
        # 1. Started Metformin 500mg OD
        record_medication_event(
            db=self.db,
            patient_id=self.patient.id,
            drug_name="Metformin",
            action="started",
            new_dose="500mg OD",
            reason="Inadequate glycemic control",
            doctor_id=self.doctor.id,
        )
        # 2. Increased Metformin to 500mg BD
        record_medication_event(
            db=self.db,
            patient_id=self.patient.id,
            drug_name="Metformin",
            action="dose_increased",
            old_dose="500mg OD",
            new_dose="500mg BD",
            reason="HbA1c remained elevated (7.8%)",
            doctor_id=self.doctor.id,
        )
        # 3. Stopped Amlodipine due to pedal edema
        record_medication_event(
            db=self.db,
            patient_id=self.patient.id,
            drug_name="Amlodipine",
            action="stopped",
            old_dose="5mg OD",
            reason="Adverse effect",
            reason_details="Pedal edema",
            doctor_id=self.doctor.id,
        )

        intel = get_medication_intelligence(self.db, self.patient.id)
        self.assertEqual(len(intel["medications"]), 2)

        amlo = next((m for m in intel["medications"] if m["drug_name"] == "Amlodipine"), None)
        self.assertIsNotNone(amlo)
        self.assertEqual(amlo["status"], "Stopped")
        self.assertEqual(amlo["stop_reason"], "Adverse effect")
        self.assertEqual(amlo["stop_details"], "Pedal edema")

        metf = next((m for m in intel["medications"] if m["drug_name"] == "Metformin"), None)
        self.assertIsNotNone(metf)
        self.assertEqual(metf["status"], "Active")
        self.assertEqual(metf["change_count"], 2)

    # ---------------------------------------------------------------------
    # Stage 4: Since Last Visit Service
    # ---------------------------------------------------------------------
    def test_changes_since_last_visit(self):
        # Previous visit 3 months ago
        enc_old = Encounter(
            patient_id=self.patient.id,
            doctor_id=self.doctor.id,
            encounter_date=datetime.utcnow() - timedelta(days=90),
            status="Completed",
        )
        self.db.add(enc_old)
        self.db.commit()

        # Lab completed recently
        lab = LabResult(
            patient_id=self.patient.id,
            test_name="Serum Creatinine",
            result_value="1.5",
            unit="mg/dL",
            status="Completed",
            result_date=datetime.utcnow() - timedelta(days=2),
        )
        self.db.add(lab)
        self.db.commit()

        changes = get_changes_since_last_visit(self.db, self.patient.id)
        self.assertEqual(len(changes.new_results), 1)
        self.assertEqual(changes.new_results[0]["test_name"], "Serum Creatinine")
        self.assertEqual(changes.new_results[0]["result_value"], "1.5")

    # ---------------------------------------------------------------------
    # Stage 7 & 8: Doctor Attention Engine & Prepare Patient
    # ---------------------------------------------------------------------
    def test_attention_engine_and_prepare_patient(self):
        # Add deteriorating creatinine (1.1 -> 1.6)
        lab_old = LabResult(
            patient_id=self.patient.id,
            test_name="Serum Creatinine",
            result_value="1.1",
            unit="mg/dL",
            reference_range="0.7 - 1.2",
            status="Completed",
            result_date=datetime.utcnow() - timedelta(days=60),
        )
        lab_new = LabResult(
            patient_id=self.patient.id,
            test_name="Serum Creatinine",
            result_value="1.6",
            unit="mg/dL",
            reference_range="0.7 - 1.2",
            status="Completed",
            result_date=datetime.utcnow() - timedelta(days=2),
        )
        # Add overdue loop
        create_open_loop(
            db=self.db,
            patient_id=self.patient.id,
            loop_type="lab",
            description="HbA1c repeat",
            expected_date=date.today() - timedelta(days=18),
        )
        self.db.add_all([lab_old, lab_new])
        self.db.commit()

        att = get_patient_attention_items(self.db, self.patient.id)
        self.assertTrue(len(att["needs_decision"]) >= 1)
        self.assertTrue(any("Creatinine" in d["title"] for d in att["needs_decision"]))

        self.assertTrue(len(att["needs_attention"]) >= 1)
        self.assertTrue(any("HbA1c" in a["title"] for a in att["needs_attention"]))

        # Cross-patient queue
        today = datetime.now(timezone(timedelta(hours=5, minutes=30))).date()
        self.db.add(Appointment(patient_id=self.patient.id, doctor_id=self.doctor.id,
                                appointment_time=datetime.combine(today, datetime.min.time())))
        self.db.commit()
        queue = get_clinic_attention_queue(self.db)
        self.assertTrue(queue.total_count >= 2)

        # Prepare Patient Brief
        brief = get_prepared_patient_brief(self.db, self.patient.id)
        self.assertEqual(brief.patient.name, "Ramesh Patil")
        self.assertEqual(brief.patient.opd_number, "OPD-1842")
        self.assertTrue(len(brief.overdue_loops) >= 1)

    # ---------------------------------------------------------------------
    # Stage 9: Patient Brain Coordinator & Doctor Corrections
    # ---------------------------------------------------------------------
    def test_patient_brain_snapshot_and_corrections(self):
        brain = get_or_build_patient_brain(self.db, self.patient.id, force_refresh=True)
        self.assertEqual(brain.patient_id, self.patient.id)
        self.assertEqual(brain.version, 1)

        # Doctor submits correction
        correction = record_brain_correction(
            db=self.db,
            patient_id=self.patient.id,
            doctor_id=self.doctor.id,
            entity_type="problem",
            entity_id=None,
            source_value="Diabetes Type 2",
            derived_value="Uncontrolled",
            doctor_correction="Patient well controlled on diet and Metformin",
        )
        self.assertEqual(correction.doctor_correction, "Patient well controlled on diet and Metformin")

        # Snapshot version increments
        updated_brain = get_or_build_patient_brain(self.db, self.patient.id)
        self.assertEqual(updated_brain.version, 2)

    # ---------------------------------------------------------------------
    # Stage 10: PG Assistant Context Router & Narrow Tools
    # ---------------------------------------------------------------------
    def test_pg_assistant_context_routing_and_state(self):
        # 1. Intent routing
        intent1, _ = route_intent("Why was amlodipine stopped?")
        self.assertEqual(intent1, "medication")

        intent2, _ = route_intent("How has creatinine been trending?")
        self.assertEqual(intent2, "labs")

        intent3, _ = route_intent("What is pending?")
        self.assertEqual(intent3, "open_loops")

        # Record medication event for query
        record_medication_event(
            db=self.db,
            patient_id=self.patient.id,
            drug_name="Amlodipine",
            action="stopped",
            old_dose="5mg",
            reason="Adverse effect",
            reason_details="Pedal edema",
            doctor_id=self.doctor.id,
        )

        resp = query_pg_assistant(
            db=self.db,
            patient_id=self.patient.id,
            doctor_id=self.doctor.id,
            question="Why was amlodipine stopped?",
        )
        self.assertEqual(resp.intent, "medication")
        self.assertTrue(any("Pedal edema" in f for f in resp.facts))
        self.assertTrue(len(resp.sources) >= 1)
        self.assertEqual(resp.sources[0].source_type, "medication_event")

        # Test server-side state on follow-up question
        conv = self.db.query(ConversationState).filter(ConversationState.patient_id == self.patient.id).first()
        self.assertIsNotNone(conv)

        # Check AI Interaction audit entry was saved
        audit = self.db.query(AIInteraction).filter(AIInteraction.patient_id == self.patient.id).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.action, "ask_pg")

    # ---------------------------------------------------------------------
    # Stage 11: AI Plan Extraction & Commitment
    # ---------------------------------------------------------------------
    def test_plan_structuring_and_commit(self):
        text = "continue metformin repeat hba1c after 3 months and review in 3 months"
        actions = extract_plan_actions_deterministic(text)
        self.assertEqual(len(actions), 3)

        act_types = [a.type for a in actions]
        self.assertIn("continue_medication", act_types)
        self.assertIn("investigation", act_types)
        self.assertIn("follow_up", act_types)

        hba1c_action = next(a for a in actions if a.type == "investigation")
        self.assertEqual(hba1c_action.test_name, "HbA1c")
        self.assertEqual(hba1c_action.due_in, "3 months")

        # Commit actions
        result = commit_plan_actions(
            db=self.db,
            patient_id=self.patient.id,
            visit_id=None,
            doctor_id=self.doctor.id,
            actions=actions,
        )
        self.assertEqual(result["status"], "committed")
        self.assertEqual(result["decisions_created"], 3)
        self.assertEqual(result["open_loops_created"], 2)


if __name__ == "__main__":
    unittest.main()
