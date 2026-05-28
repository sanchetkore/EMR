from sqlalchemy.orm import Session
from app.core.database import SessionLocal, engine
from app.models import user, patient, clinical
from app.core.security import get_password_hash

def seed_db():
    # Create tables
    user.Base.metadata.create_all(bind=engine)
    patient.Base.metadata.create_all(bind=engine)
    clinical.Base.metadata.create_all(bind=engine)
    
    from app.models.settings import SystemSetting
    SystemSetting.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # Check if roles exist
        admin_role = db.query(user.Role).filter(user.Role.name == "Admin").first()
        doctor_role = db.query(user.Role).filter(user.Role.name == "Doctor").first()
        frontdesk_role = db.query(user.Role).filter(user.Role.name == "Frontdesk").first()

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
            "manage_users": [admin_role],
            "manage_templates": [admin_role, doctor_role],
            "view_templates": [admin_role, doctor_role, frontdesk_role]
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

    finally:
        db.close()

if __name__ == "__main__":
    print("Seeding database...")
    seed_db()
    print("Seeding completed.")
