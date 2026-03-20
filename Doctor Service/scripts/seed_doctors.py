"""
Seed data script for Doctor Service.
Run inside the docker container:
  docker exec doctor_service python /app/scripts/seed_doctors.py
"""
import asyncio
import uuid
import sys
import os
from datetime import time

sys.path.insert(0, "/app")

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@postgres:5432/doctor_db"
)

engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

# ── Seed data ────────────────────────────────────────────────────────────────

SPECIALTIES = [
    {"id": str(uuid.uuid4()), "name": "Cardiology",         "description": "Diagnosis and treatment of heart and cardiovascular diseases"},
    {"id": str(uuid.uuid4()), "name": "Neurology",           "description": "Treatment of nervous system disorders"},
    {"id": str(uuid.uuid4()), "name": "Pediatrics",          "description": "Healthcare for children aged 0-16 years"},
    {"id": str(uuid.uuid4()), "name": "Internal Medicine",   "description": "General internal medicine and chronic disease management"},
    {"id": str(uuid.uuid4()), "name": "General Surgery",     "description": "Surgical procedures and post-operative care"},
    {"id": str(uuid.uuid4()), "name": "Dermatology",         "description": "Diagnosis and treatment of skin conditions"},
    {"id": str(uuid.uuid4()), "name": "ENT",                 "description": "Ear, nose, and throat disorders"},
    {"id": str(uuid.uuid4()), "name": "Ophthalmology",       "description": "Eye care and ophthalmic surgery"},
]

DOCTORS = [
    {
        "user_id": str(uuid.uuid4()),
        "full_name": "Dr. Andrew Nguyen",
        "title": "MD, PhD",
        "specialty": "Cardiology",
        "experience_years": 15,
        "schedules": [
            {"day": "MONDAY",    "start": time(8, 0),  "end": time(12, 0)},
            {"day": "WEDNESDAY", "start": time(8, 0),  "end": time(12, 0)},
            {"day": "FRIDAY",    "start": time(13, 0), "end": time(17, 0)},
        ],
    },
    {
        "user_id": str(uuid.uuid4()),
        "full_name": "Dr. Emily Tran",
        "title": "MD, Assoc. Prof.",
        "specialty": "Neurology",
        "experience_years": 20,
        "schedules": [
            {"day": "TUESDAY",  "start": time(8, 0),  "end": time(11, 30)},
            {"day": "THURSDAY", "start": time(8, 0),  "end": time(11, 30)},
        ],
    },
    {
        "user_id": str(uuid.uuid4()),
        "full_name": "Dr. Michael Le",
        "title": "MD",
        "specialty": "Pediatrics",
        "experience_years": 10,
        "schedules": [
            {"day": "MONDAY",    "start": time(7, 30), "end": time(11, 30)},
            {"day": "WEDNESDAY", "start": time(13, 0), "end": time(17, 0)},
            {"day": "FRIDAY",    "start": time(7, 30), "end": time(11, 30)},
        ],
    },
    {
        "user_id": str(uuid.uuid4()),
        "full_name": "Dr. Robert Pham",
        "title": "MD, Prof.",
        "specialty": "Internal Medicine",
        "experience_years": 25,
        "schedules": [
            {"day": "TUESDAY",  "start": time(8, 0),  "end": time(12, 0)},
            {"day": "THURSDAY", "start": time(8, 0),  "end": time(12, 0)},
            {"day": "SATURDAY", "start": time(8, 0),  "end": time(11, 0)},
        ],
    },
    {
        "user_id": str(uuid.uuid4()),
        "full_name": "Dr. Sarah Hoang",
        "title": "MD",
        "specialty": "Dermatology",
        "experience_years": 12,
        "schedules": [
            {"day": "MONDAY", "start": time(13, 0), "end": time(17, 0)},
            {"day": "FRIDAY", "start": time(13, 0), "end": time(17, 0)},
        ],
    },
    {
        "user_id": str(uuid.uuid4()),
        "full_name": "Dr. James Vu",
        "title": "MD, Spec. II",
        "specialty": "General Surgery",
        "experience_years": 18,
        "schedules": [
            {"day": "WEDNESDAY", "start": time(7, 0),   "end": time(11, 0)},
            {"day": "THURSDAY",  "start": time(13, 30), "end": time(17, 0)},
        ],
    },
]


# ── Main ──────────────────────────────────────────────────────────────────────

async def seed():
    async with SessionLocal() as session:
        result = await session.execute(text("SELECT COUNT(*) FROM specialties"))
        count = result.scalar()
        if count > 0:
            print(f"Specialties already exist ({count} records). Skipping seed.")
            return

        print("Seeding specialties...")
        specialty_map = {}
        for s in SPECIALTIES:
            await session.execute(text(
                "INSERT INTO specialties (id, name, description) VALUES (:id, :name, :description)"
            ), {"id": s["id"], "name": s["name"], "description": s["description"]})
            specialty_map[s["name"]] = s["id"]
            print(f"  + {s['name']}")

        print("\nSeeding doctors and schedules...")
        for d in DOCTORS:
            specialty_id = specialty_map.get(d["specialty"])
            await session.execute(text(
                "INSERT INTO doctors (user_id, specialty_id, full_name, title, experience_years) "
                "VALUES (:user_id, :specialty_id, :full_name, :title, :experience_years)"
            ), {
                "user_id": d["user_id"],
                "specialty_id": specialty_id,
                "full_name": d["full_name"],
                "title": d["title"],
                "experience_years": d["experience_years"],
            })

            for sched in d["schedules"]:
                await session.execute(text(
                    "INSERT INTO doctor_schedules (id, doctor_id, day_of_week, start_time, end_time, slot_duration_minutes) "
                    "VALUES (:id, :doctor_id, :day_of_week, :start_time, :end_time, 30)"
                ), {
                    "id": str(uuid.uuid4()),
                    "doctor_id": d["user_id"],
                    "day_of_week": sched["day"],
                    "start_time": sched["start"],
                    "end_time": sched["end"],
                })
            print(f"  + {d['full_name']} ({d['specialty']}) - {len(d['schedules'])} schedules")

        await session.commit()

    print("\nSeed completed successfully!")
    print("\nDoctor list:")
    for d in DOCTORS:
        print(f"   {d['full_name']} | user_id: {d['user_id']}")


if __name__ == "__main__":
    asyncio.run(seed())
