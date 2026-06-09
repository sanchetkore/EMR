from sqlalchemy.orm import sessionmaker
from app.core.database import Base, engine, SessionLocal
from app.models.user import User, Role, UserTab
import os

def migrate():
    # Ensure tables are created
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    users = db.query(User).all()
    
    for user in users:
        # Check if user already has tabs assigned
        existing = db.query(UserTab).filter(UserTab.user_id == user.id).count()
        if existing > 0:
            continue
            
        role_name = user.role.name.lower() if user.role and user.role.name else ""
        tabs = []
        
        # Default Logic (similar to Layout.tsx previous logic)
        if role_name == "frontdesk":
            tabs = ['appointments', 'patients', 'billing', 'pharmacy']
        elif "doctor" in role_name:
            tabs = ['dashboard', 'patients', 'appointments', 'billing', 'labs', 'pharmacy', 'reports', 'settings']
        elif "admin" in role_name:
            tabs = ['dashboard', 'patients', 'appointments', 'billing', 'labs', 'pharmacy', 'reports', 'settings']
        elif "lab" in role_name:
            tabs = ['dashboard', 'patients', 'labs']
        elif "pharmacist" in role_name:
            tabs = ['dashboard', 'patients', 'pharmacy']
        else:
            tabs = ['dashboard', 'patients']
            
        # Create tabs
        for tab in tabs:
            db.add(UserTab(user_id=user.id, tab_name=tab))
            
    db.commit()
    print("Migration completed.")

if __name__ == "__main__":
    migrate()
