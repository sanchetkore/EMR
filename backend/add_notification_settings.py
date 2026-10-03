from dotenv import load_dotenv
load_dotenv()
from sqlalchemy import text
from app.core.database import engine

def migrate():
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE clinic_profile ADD COLUMN notification_settings JSONB"))
            conn.commit()
            print("Successfully added notification_settings column to clinic_profile")
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                print("notification_settings column already exists")
            else:
                print(f"Error: {e}")

if __name__ == "__main__":
    migrate()
