from sqlalchemy import text
from app.core.database import engine

def migrate():
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE appointments ADD COLUMN token_number VARCHAR"))
            conn.commit()
            print("Successfully added token_number column to appointments")
        except Exception as e:
            if "already exists" in str(e) or "duplicate column" in str(e):
                print("token_number column already exists")
            else:
                print(f"Error: {e}")

if __name__ == "__main__":
    migrate()
