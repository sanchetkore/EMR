import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

from sqlalchemy import text
from app.core.database import engine

def migrate():
    with engine.connect() as conn:
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS patient_ai_summaries (
                    id SERIAL PRIMARY KEY,
                    patient_id INTEGER REFERENCES patients(id) ON DELETE CASCADE,
                    summary_text TEXT NOT NULL,
                    last_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
            print("Successfully created patient_ai_summaries table")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    migrate()
