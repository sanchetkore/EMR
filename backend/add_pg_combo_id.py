from app.core.database import engine
from sqlalchemy import text

def migrate():
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE lab_results ADD COLUMN combo_id INTEGER REFERENCES combo_lab_tests(id);"))
            conn.commit()
            print("Successfully added combo_id to PostgreSQL lab_results table.")
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                print("Column combo_id already exists.")
            else:
                print(f"Error: {e}")

if __name__ == "__main__":
    migrate()
