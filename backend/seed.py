import os
from sqlalchemy.orm import Session
from app.core.database import SessionLocal, engine
from app.models import user, patient, clinical, lab_result, mobile
from sqlalchemy import inspect, text
from app.models.lis_connector import LISConnector, PatientExternalIdentity, ExternalLabOrder
from app.core.security import LEGACY_DEMO_PASSWORDS, get_password_hash, verify_password
from app.core.lis_migrations import migrate_patient_identity_uniqueness

def run_emr_auto_migrations():
    """Ensure missing columns and constraints on existing tables are added safely."""
    from app.core.encounter_migrations import migrate_encounter_lifecycle
    from app.core.patient_brain_migrations import migrate_patient_brain
    try:
        with engine.begin() as conn:
            if conn.dialect.name == "sqlite" and not conn.connection.driver_connection.in_transaction:
                conn.exec_driver_sql("BEGIN")
            inspector = inspect(conn)
            migrate_encounter_lifecycle(conn)
            migrate_patient_brain(conn)
            if inspector.has_table("invoices"):
                invoice_cols = {col["name"] for col in inspector.get_columns("invoices")}
                if "service_date" not in invoice_cols:
                    conn.execute(text("ALTER TABLE invoices ADD COLUMN service_date DATE"))
            if inspector.has_table("lis_connector"):
                cols = {col["name"] for col in inspector.get_columns("lis_connector")}
                if "configured_mode" not in cols:
                    conn.execute(text("ALTER TABLE lis_connector ADD COLUMN configured_mode VARCHAR(32) DEFAULT 'CONNECTED'"))
                if "last_health_status" not in cols:
                    conn.execute(text("ALTER TABLE lis_connector ADD COLUMN last_health_status VARCHAR(32) DEFAULT 'UNKNOWN'"))
                if "last_health_check" not in cols:
                    conn.execute(text("ALTER TABLE lis_connector ADD COLUMN last_health_check TIMESTAMP"))
                if "last_catalog_refresh" not in cols:
                    conn.execute(text("ALTER TABLE lis_connector ADD COLUMN last_catalog_refresh TIMESTAMP"))

            if inspector.has_table("patients"):
                cols = {col["name"] for col in inspector.get_columns("patients")}
                if "opd_number" not in cols:
                    conn.execute(text("ALTER TABLE patients ADD COLUMN opd_number VARCHAR"))
                # Clean up empty strings to NULL and ensure partial unique index
                conn.execute(text("UPDATE patients SET opd_number = NULL WHERE opd_number IS NOT NULL AND trim(opd_number) = ''"))
                conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_patient_opd ON patients(opd_number) WHERE opd_number IS NOT NULL"))

            if inspector.has_table("patient_external_identities"):
                cols = {col["name"] for col in inspector.get_columns("patient_external_identities")}
                if "lis_host" not in cols:
                    conn.execute(text("ALTER TABLE patient_external_identities ADD COLUMN lis_host VARCHAR(128) DEFAULT ''"))
                migrate_patient_identity_uniqueness(conn)
                conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_patient_lis_host ON patient_external_identities(patient_id, lis_host)"))

            if inspector.has_table("external_lab_orders"):
                cols = {col["name"] for col in inspector.get_columns("external_lab_orders")}
                if "lis_host" not in cols:
                    conn.execute(text("ALTER TABLE external_lab_orders ADD COLUMN lis_host VARCHAR(128) DEFAULT ''"))
                if "payload_hash" not in cols:
                    conn.execute(text("ALTER TABLE external_lab_orders ADD COLUMN payload_hash VARCHAR(64)"))
    except Exception as e:
        raise RuntimeError("EMR schema upgrade failed; startup stopped to avoid unsafe LIS mappings") from e

def seed_db():
    # Create tables
    user.Base.metadata.create_all(bind=engine)
    patient.Base.metadata.create_all(bind=engine)
    clinical.Base.metadata.create_all(bind=engine)
    lab_result.Base.metadata.create_all(bind=engine)
    mobile.Base.metadata.create_all(bind=engine)
    LISConnector.metadata.create_all(bind=engine)
    PatientExternalIdentity.metadata.create_all(bind=engine)
    ExternalLabOrder.metadata.create_all(bind=engine)

    from app.models.settings import SystemSetting
    SystemSetting.metadata.create_all(bind=engine)

    run_emr_auto_migrations()

    db = SessionLocal()
    try:
        # Check if roles exist
        admin_role = db.query(user.Role).filter(user.Role.name == "Admin").first()
        doctor_role = db.query(user.Role).filter(user.Role.name == "Doctor").first()
        frontdesk_role = db.query(user.Role).filter(user.Role.name == "Frontdesk").first()
        pharmacist_role = db.query(user.Role).filter(user.Role.name == "Pharmacist").first()

        roles_to_add = []
        if not admin_role:
            admin_role = user.Role(name="Admin")
            roles_to_add.append(admin_role)
        if not doctor_role:
            doctor_role = user.Role(name="Doctor")
            roles_to_add.append(doctor_role)
        if not frontdesk_role:
            frontdesk_role = user.Role(name="Frontdesk")
            roles_to_add.append(frontdesk_role)
        if not pharmacist_role:
            pharmacist_role = user.Role(name="Pharmacist")
            roles_to_add.append(pharmacist_role)

        if roles_to_add:
            db.add_all(roles_to_add)
            db.commit()

        # Check and create permissions
        perms = {
            "manage_patients": [frontdesk_role],
            "view_patients": [frontdesk_role, doctor_role],
            "manage_appointments": [frontdesk_role],
            "view_appointments": [frontdesk_role, doctor_role],
            "manage_clinical": [doctor_role],
            "view_clinical": [doctor_role],
            "manage_billing": [frontdesk_role],
            "view_billing": [frontdesk_role],
            "delete_billing": [admin_role], # NEW: Only admin can delete bills
            "manage_users": [admin_role],
            "manage_templates": [admin_role, doctor_role],
            "view_templates": [admin_role, doctor_role, frontdesk_role],
            "manage_pharmacy": [pharmacist_role],
            "view_pharmacy": [pharmacist_role, doctor_role],
            "view_dashboard": [admin_role, doctor_role, frontdesk_role]
        }

        for perm_name, roles in perms.items():
            perm = db.query(user.Permission).filter(user.Permission.name == perm_name).first()
            if not perm:
                perm = user.Permission(name=perm_name)
                db.add(perm)
                db.commit()

            for role in roles:
                if role and perm not in role.permissions:
                    role.permissions.append(perm)
        db.commit()

        bootstrap_password = os.getenv("EMR_BOOTSTRAP_ADMIN_PASSWORD")
        if bootstrap_password and (
            not 16 <= len(bootstrap_password.encode("utf-8")) <= 72
            or bootstrap_password in LEGACY_DEMO_PASSWORDS.values()
        ):
            raise ValueError("EMR_BOOTSTRAP_ADMIN_PASSWORD must contain 16 to 72 UTF-8 bytes")

        legacy_users = db.query(user.User).filter(user.User.username.in_(LEGACY_DEMO_PASSWORDS)).all()
        existing_admin = next((account for account in legacy_users if account.username == "admin"), None)
        for account in legacy_users:
            if not account.hashed_password or not verify_password(LEGACY_DEMO_PASSWORDS[account.username], account.hashed_password):
                continue
            db.query(user.AuthSession).filter(
                user.AuthSession.user_id == account.id, user.AuthSession.revoked.is_(False)
            ).update({user.AuthSession.revoked: True}, synchronize_session=False)
            if account.username == "admin" and bootstrap_password and account.role_id == admin_role.id:
                account.hashed_password = get_password_hash(bootstrap_password)

        if existing_admin is None and bootstrap_password:
            db.add(user.User(
                username="admin",
                email="admin@emr.com",
                hashed_password=get_password_hash(bootstrap_password),
                role_id=admin_role.id,
            ))
        db.commit()

        # Create default system settings
        from app.models.settings import SystemSetting
        default_settings = {
            "slot_duration_minutes": "30",
            "start_time": "08:00",
            "end_time": "20:00"
        }
        for k, v in default_settings.items():
            db_setting = db.query(SystemSetting).filter(SystemSetting.key == k).first()
            if not db_setting:
                db_setting = SystemSetting(key=k, value=v)
                db.add(db_setting)
        db.commit()

        # Seed Appointment Statuses
        from app.models.patient import AppointmentStatusConfig
        default_statuses = ["Scheduled", "Waiting", "Ongoing", "Completed", "Cancelled", "No Show"]
        for status_name in default_statuses:
            status_obj = db.query(AppointmentStatusConfig).filter(AppointmentStatusConfig.name == status_name).first()
            if not status_obj:
                db.add(AppointmentStatusConfig(name=status_name, color="#000000"))
        db.commit()

        # Seed Vital Configurations
        from app.models.encounter import VitalConfiguration
        default_vitals = [
            {"name": "Blood Pressure", "data_type": "string", "formula": None},
            {"name": "Temperature", "data_type": "float", "formula": None},
            {"name": "Heart Rate", "data_type": "integer", "formula": None},
            {"name": "Height (cm)", "data_type": "float", "formula": None},
            {"name": "Weight (kg)", "data_type": "float", "formula": None},
            {"name": "BMI", "data_type": "computed", "formula": "Weight (kg) / ((Height (cm)/100) * (Height (cm)/100))"}
        ]
        for v in default_vitals:
            vital_obj = db.query(VitalConfiguration).filter(VitalConfiguration.name == v["name"]).first()
            if not vital_obj:
                db.add(VitalConfiguration(**v))
        db.commit()

    finally:
        db.close()

if __name__ == "__main__":
    print("Seeding database...")
    seed_db()
    print("Seeding completed.")
