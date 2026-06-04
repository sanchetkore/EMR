from sqlalchemy import text
from app.core.database import engine

def migrate():
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE prescriptions ADD COLUMN status VARCHAR DEFAULT 'Pending'"))
            conn.commit()
            print("Successfully added status column to prescriptions")
        except Exception as e:
            if "already exists" in str(e) or "duplicate column" in str(e):
                print("status column already exists")
            else:
                print(f"Error: {e}")

if __name__ == "__main__":
    migrate()
