from sqlalchemy.orm import Session
from app.core.database import SessionLocal, engine
from app.models import user, patient, clinical, lab_result
from app.core.security import get_password_hash

def seed_db():
    # Create tables
    user.Base.metadata.create_all(bind=engine)
    patient.Base.metadata.create_all(bind=engine)
    clinical.Base.metadata.create_all(bind=engine)
    lab_result.Base.metadata.create_all(bind=engine)
    
    from app.models.settings import SystemSetting
    SystemSetting.metadata.create_all(bind=engine)

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
            "view_pharmacy": [pharmacist_role, doctor_role]
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

        # Check if admin user exists
        admin_user = db.query(user.User).filter(user.User.username == "admin").first()
        if not admin_user:
            admin_user = user.User(
                username="admin",
                email="admin@emr.com",
                hashed_password=get_password_hash("admin123"),
                role_id=admin_role.id
            )
            db.add(admin_user)
            db.commit()
            
        doctor_user = db.query(user.User).filter(user.User.username == "doctor").first()
        if not doctor_user:
            doctor_user = user.User(
                username="doctor",
                email="doctor@emr.com",
                hashed_password=get_password_hash("doctor123"),
                role_id=doctor_role.id
            )
            db.add(doctor_user)
            db.commit()
            
        frontdesk_user = db.query(user.User).filter(user.User.username == "frontdesk").first()
        if not frontdesk_user:
            frontdesk_user = user.User(
                username="frontdesk",
                email="frontdesk@emr.com",
                hashed_password=get_password_hash("frontdesk123"),
                role_id=frontdesk_role.id
            )
            db.add(frontdesk_user)
            db.commit()
            
        pharmacist_user = db.query(user.User).filter(user.User.username == "pharmacist").first()
        if not pharmacist_user:
            pharmacist_user = user.User(
                username="pharmacist",
                email="pharmacist@emr.com",
                hashed_password=get_password_hash("pharmacist123"),
                role_id=pharmacist_role.id
            )
            db.add(pharmacist_user)
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
