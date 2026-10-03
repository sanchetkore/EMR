import os
import sys
from dotenv import load_dotenv

# Add the backend directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

# Manually format DATABASE_URL if needed because it relies on variable expansion in .env
db_url = os.environ.get("DATABASE_URL")
if db_url and "${POSTGRES_USER}" in db_url:
    db_url = db_url.replace("${POSTGRES_USER}", os.environ.get("POSTGRES_USER", ""))
    db_url = db_url.replace("${POSTGRES_PASSWORD}", os.environ.get("POSTGRES_PASSWORD", ""))
    db_url = db_url.replace("${POSTGRES_DB}", os.environ.get("POSTGRES_DB", ""))
    os.environ["DATABASE_URL"] = db_url

from app.core.database import engine
from app.models.whatsapp_template import WhatsappTemplate

print(f"Using database URL: {os.environ.get('DATABASE_URL')}")
try:
    WhatsappTemplate.__table__.create(bind=engine, checkfirst=True)
    print("Created whatsapp_templates table successfully in target database.")
except Exception as e:
    print(f"Error creating table: {e}")
