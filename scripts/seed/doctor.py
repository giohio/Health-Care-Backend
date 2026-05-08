"""Seed doctor DB — specialties, profiles, schedules, availability, services."""
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from .constants import SPECIALTIES
from .db_urls import _doctor_db_url, _t
from .doctors import DOCTORS


async def seed_doctor_db(user_ids: dict[str, str]) -> dict[str, str]:
    """Insert specialties, doctor profiles, schedules, availability, service offerings.

    Returns {doctor_email: specialty_id}.
    """
    specialty_ids: dict[str, str] = {}
    engine = create_async_engine(_doctor_db_url(), echo=False)
    try:
        async with engine.begin() as conn:
            # Specialties
            for sp in SPECIALTIES:
                sp_id = str(uuid.uuid4())
                await conn.execute(
                    text("""
                        INSERT INTO specialties (id, name, description)
                        VALUES (:id, :name, :desc)
                        ON CONFLICT (name) DO NOTHING
                    """),
                    {"id": sp_id, "name": sp["name"], "desc": sp["description"]},
                )
                row = await conn.execute(
                    text("SELECT id FROM specialties WHERE name = :n"), {"n": sp["name"]}
                )
                specialty_ids[sp["name"]] = str(row.scalar_one())
            print(f"  [doctor] Seeded {len(SPECIALTIES)} specialties.")

            for doc in DOCTORS:
                user_id = user_ids[doc["email"]]
                sp_id = specialty_ids[doc["specialty"]]

                # Doctor profile
                await conn.execute(
                    text("""
                        INSERT INTO doctors (user_id, specialty_id, full_name, title,
                            experience_years, auto_confirm, confirmation_timeout_minutes,
                            average_rating, rating_count)
                        VALUES (:uid, :sp, :name, :title, :exp, :ac, 15, 0.0, 0)
                        ON CONFLICT (user_id) DO UPDATE
                            SET specialty_id      = EXCLUDED.specialty_id,
                                full_name         = EXCLUDED.full_name,
                                title             = EXCLUDED.title,
                                experience_years  = EXCLUDED.experience_years,
                                auto_confirm      = EXCLUDED.auto_confirm
                    """),
                    {
                        "uid": user_id, "sp": sp_id,
                        "name": doc["full_name"], "title": doc["title"],
                        "exp": doc["experience"], "ac": doc["auto_confirm"],
                    },
                )

                # Schedules
                sch = doc["schedule"]
                await conn.execute(
                    text("DELETE FROM doctor_schedules WHERE doctor_id = :uid"), {"uid": user_id}
                )
                for day_name in sch["days"]:
                    await conn.execute(
                        text("""
                            INSERT INTO doctor_schedules
                                (id, doctor_id, day_of_week, start_time, end_time, slot_duration_minutes)
                            VALUES (:id, :uid, :dow, :start, :end, :slot)
                        """),
                        {
                            "id": str(uuid.uuid4()), "uid": user_id, "dow": day_name,
                            "start": _t(sch["start"]), "end": _t(sch["end"]), "slot": sch["slot"],
                        },
                    )

                # Availability
                av = doc["availability"]
                await conn.execute(
                    text("DELETE FROM doctor_availability WHERE doctor_id = :uid"), {"uid": user_id}
                )
                for dow_int in av["days"]:
                    await conn.execute(
                        text("""
                            INSERT INTO doctor_availability
                                (id, doctor_id, day_of_week, start_time, end_time,
                                 break_start, break_end, max_patients, is_active,
                                 created_at, updated_at)
                            VALUES (:id, :uid, :dow, :start, :end,
                                    :bs, :be, :mp, TRUE, NOW(), NOW())
                        """),
                        {
                            "id": str(uuid.uuid4()), "uid": user_id, "dow": dow_int,
                            "start": _t(av["start"]), "end": _t(av["end"]),
                            "bs": _t(av["break_start"]), "be": _t(av["break_end"]),
                            "mp": av["max_patients"],
                        },
                    )

                # Service offerings
                await conn.execute(
                    text("DELETE FROM doctor_service_offerings WHERE doctor_id = :uid"), {"uid": user_id}
                )
                for svc in doc["services"]:
                    await conn.execute(
                        text("""
                            INSERT INTO doctor_service_offerings
                                (id, doctor_id, service_name, duration_minutes, fee,
                                 is_active, created_at, updated_at)
                            VALUES (:id, :uid, :name, :dur, :fee, TRUE, NOW(), NOW())
                        """),
                        {
                            "id": str(uuid.uuid4()), "uid": user_id,
                            "name": svc["name"], "dur": svc["duration"], "fee": svc["fee"],
                        },
                    )

            print(f"  [doctor] Seeded {len(DOCTORS)} doctor profiles with schedules & services.")
    finally:
        await engine.dispose()

    return {doc["email"]: specialty_ids[doc["specialty"]] for doc in DOCTORS}
