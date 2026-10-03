import os
import sys
import logging
from datetime import date, timedelta
from dotenv import load_dotenv

# Add the backend directory to sys.path
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
load_dotenv()

# Manually format DATABASE_URL if needed because it relies on variable expansion in .env
db_url = os.environ.get("DATABASE_URL")
if db_url and "${POSTGRES_USER}" in db_url:
    db_url = db_url.replace("${POSTGRES_USER}", os.environ.get("POSTGRES_USER", ""))
    db_url = db_url.replace("${POSTGRES_PASSWORD}", os.environ.get("POSTGRES_PASSWORD", ""))
    db_url = db_url.replace("${POSTGRES_DB}", os.environ.get("POSTGRES_DB", ""))
    os.environ["DATABASE_URL"] = db_url

from app.core.database import SessionLocal
from app.models.clinic import ClinicProfile
from app.models.encounter import Encounter
from app.services.whatsapp_service import send_followup_reminder_whatsapp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    logger.info("Starting followup reminders job...")
    db = SessionLocal()
    try:
        profile = db.query(ClinicProfile).filter(ClinicProfile.id == 1).first()
        if not profile or not profile.notification_settings:
            logger.info("Clinic profile or notification settings not configured.")
            return

        settings = profile.notification_settings
        reminder_settings = settings.get("send_followup_reminder", {})
        if not reminder_settings.get("whatsapp"):
            logger.info("WhatsApp follow-up reminders are disabled.")
            return

        days_early = reminder_settings.get("days_early", 1)
        target_date = date.today() + timedelta(days=days_early)
        logger.info(f"Checking for follow-ups on target date: {target_date}")

        encounters = db.query(Encounter).filter(Encounter.followup_date == target_date).all()
        logger.info(f"Found {len(encounters)} encounters with follow-ups on {target_date}.")

        for enc in encounters:
            if enc.patient_id and enc.doctor_id:
                logger.info(f"Sending reminder for Encounter {enc.id}, Patient {enc.patient_id}")
                send_followup_reminder_whatsapp(
                    patient_id=enc.patient_id,
                    doctor_id=enc.doctor_id,
                    followup_date=enc.followup_date
                )

        logger.info("Finished followup reminders job.")
    except Exception as e:
        logger.error(f"Error in followup reminders job: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
