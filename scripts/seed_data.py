#!/usr/bin/env python3
"""Entry point -- orchestrates all seed modules.

Usage:
    python scripts/seed_data.py

Requires .env at repo root (POSTGRES_USER/PASSWORD, etc.).
All Postgres databases must be reachable on localhost:5432.
"""
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
from pwdlib import PasswordHash

sys.path.insert(0, str(Path(__file__).resolve().parent))

from seed.auth        import seed_auth_db
from seed.doctor      import seed_doctor_db
from seed.patient     import seed_patient_db, seed_patient_vitals
from seed.appointment import seed_appointment_db
from seed.emr         import seed_emr_db
from seed.clinical    import seed_clinical_db
from seed.triage      import seed_triage_sessions, seed_chat_sessions
from seed.cleanup     import cleanup_all
from seed.payment     import seed_payment_db
from seed.summary     import print_summary
from sync_names       import sync_names


async def main() -> None:
    hasher = PasswordHash.recommended()

    # Cleanup first
    await cleanup_all()

    print("Seeding Auth database (admin + doctors + patients)...")
    user_ids = await seed_auth_db(hasher)

    print("Seeding Doctor database (specialties, profiles, schedules, services)...")
    doctor_specialty_ids = await seed_doctor_db(user_ids)

    print("Seeding Patient database (profiles + health backgrounds)...")
    patient_data = await seed_patient_db(user_ids)

    print("Seeding Patient vitals (historical readings)...")
    await seed_patient_vitals(user_ids, patient_data)

    print("Seeding Appointment database...")
    completed_appointments, in_progress_appointments = await seed_appointment_db(patient_data, user_ids, doctor_specialty_ids)

    print("Seeding Payment database (lab fee configs)...")
    await seed_payment_db()

    print("Seeding EMR Result database (lab orders + results)...")
    await seed_emr_db(completed_appointments, user_ids, in_progress_appointments)

    print("Seeding Clinical database (diagnoses, medications, notes)...")
    await seed_clinical_db(user_ids)

    print("Seeding AI Service database (triage sessions + chat sessions)...")
    triage_sessions = await seed_triage_sessions(user_ids)
    chat_count = await seed_chat_sessions(user_ids)

    print("Syncing names across services...")
    await sync_names()

    print_summary(user_ids, patient_data, triage_sessions)


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parent.parent
    load_dotenv(repo_root / ".env")

    try:
        asyncio.run(main())
    except Exception as exc:
        print(f"Seed failed: {exc}")
        print("Make sure Postgres is running and all migrations have been applied.")
        sys.exit(1)
