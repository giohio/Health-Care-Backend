"""Cleanup script — truncates all tables before seeding."""
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from .db_urls import (
    _auth_db_url,
    _doctor_db_url,
    _patient_db_url,
    _appointment_db_url,
    _emr_db_url,
    _clinical_db_url,
    _ai_db_url,
    _payment_db_url,
)

async def clear_database(url: str, tables: list[str]) -> None:
    """Truncate tables in a database (skips tables that don't exist yet)."""
    engine = create_async_engine(url, echo=False)
    cleared = 0
    try:
        async with engine.begin() as conn:
            for table in tables:
                # Use an anonymous DO block so a missing table is silently skipped
                # without aborting the transaction for the remaining tables.
                await conn.execute(text(f"""
                    DO $$ BEGIN
                        TRUNCATE TABLE {table} CASCADE;
                    EXCEPTION WHEN undefined_table THEN NULL;
                    END $$;
                """))
                cleared += 1
        print(f"  [cleanup] Cleared {cleared} tables in {url.split('/')[-1]}")
    except Exception as e:
        print(f"  [cleanup] Failed to clear {url.split('/')[-1]}: {e}")
    finally:
        await engine.dispose()

async def cleanup_all() -> None:
    """Clear all databases in the system."""
    print("Starting system-wide cleanup...")
    
    tasks = [
        clear_database(_auth_db_url(), ["users"]),
        clear_database(_doctor_db_url(), ["doctor_schedules", "doctor_availability", "doctor_service_offerings", "doctors", "specialties"]),
        clear_database(_patient_db_url(), ["patient_vitals", "patient_health_backgrounds", "patient_profiles"]),
        clear_database(_appointment_db_url(), ["appointments"]),
        clear_database(_payment_db_url(), ["payment_transactions", "payments", "outbox_events", "lab_fee_configs"]),
        clear_database(_emr_db_url(), ["lab_results", "lab_orders", "appointment_lab_summaries"]),
        clear_database(_clinical_db_url(), ["clinical_notes", "medications", "diagnoses"]),
        clear_database(_ai_db_url(), ["triage_sessions", "chat_sessions"]),
    ]
    
    await asyncio.gather(*tasks)
    print("Cleanup complete.")
