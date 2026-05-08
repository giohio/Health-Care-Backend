"""Seed auth DB — admin + doctor + patient user accounts."""
import uuid

from pwdlib import PasswordHash
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from .constants import ADMIN
from .db_urls import _auth_db_url
from .doctors import DOCTORS
from .patients import PATIENTS


async def seed_auth_db(hasher: PasswordHash) -> dict[str, str]:
    """Insert admin + doctor + patient accounts into auth DB.

    Returns {email: user_id} for every seeded user.
    """
    engine = create_async_engine(_auth_db_url(), echo=False)
    ids: dict[str, str] = {}
    try:
        async with engine.begin() as conn:
            # Ensure full_name column exists (for older DB versions)
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR(255)"))

            # Admin
            admin_id = str(uuid.uuid4())
            await conn.execute(
                text("""
                    INSERT INTO users (id, email, hashed_password, full_name, role,
                        is_active, is_deleted, is_email_verified, is_profile_completed,
                        created_at, updated_at)
                    VALUES (:id, :email, :pwd, :name, 'admin',
                        TRUE, FALSE, TRUE, TRUE, NOW(), NOW())
                    ON CONFLICT (email) DO UPDATE
                        SET hashed_password = EXCLUDED.hashed_password,
                            full_name = EXCLUDED.full_name,
                            role = 'admin', is_active = TRUE, is_deleted = FALSE,
                            is_email_verified = TRUE, updated_at = NOW()
                """),
                {"id": admin_id, "email": ADMIN["email"], "pwd": hasher.hash(ADMIN["password"]), "name": "System Admin"},
            )
            row = await conn.execute(
                text("SELECT id FROM users WHERE email = :e"), {"e": ADMIN["email"]}
            )
            ids[ADMIN["email"]] = str(row.scalar_one())

            # Doctors
            for doc in DOCTORS:
                doc_id = str(uuid.uuid4())
                await conn.execute(
                    text("""
                        INSERT INTO users (id, email, hashed_password, full_name, role,
                            is_active, is_deleted, is_email_verified, is_profile_completed,
                            created_at, updated_at)
                        VALUES (:id, :email, :pwd, :name, 'doctor',
                            TRUE, FALSE, TRUE, TRUE, NOW(), NOW())
                        ON CONFLICT (email) DO UPDATE
                            SET hashed_password = EXCLUDED.hashed_password,
                                full_name = EXCLUDED.full_name,
                                role = 'doctor', is_active = TRUE, is_deleted = FALSE,
                                is_email_verified = TRUE, updated_at = NOW()
                    """),
                    {"id": doc_id, "email": doc["email"], "pwd": hasher.hash(doc["password"]), "name": doc["full_name"]},
                )
                row = await conn.execute(
                    text("SELECT id FROM users WHERE email = :e"), {"e": doc["email"]}
                )
                ids[doc["email"]] = str(row.scalar_one())

            # Patients
            for p in PATIENTS:
                p_id = str(uuid.uuid4())
                await conn.execute(
                    text("""
                        INSERT INTO users (id, email, hashed_password, full_name, role,
                            is_active, is_deleted, is_email_verified, is_profile_completed,
                            created_at, updated_at)
                        VALUES (:id, :email, :pwd, :name, 'patient',
                            TRUE, FALSE, TRUE, TRUE, NOW(), NOW())
                        ON CONFLICT (email) DO UPDATE
                            SET hashed_password = EXCLUDED.hashed_password,
                                full_name = EXCLUDED.full_name,
                                role = 'patient', is_active = TRUE, is_deleted = FALSE,
                                is_email_verified = TRUE, updated_at = NOW()
                    """),
                    {"id": p_id, "email": p["email"], "pwd": hasher.hash(p["password"]), "name": p["full_name"]},
                )
                row = await conn.execute(
                    text("SELECT id FROM users WHERE email = :e"), {"e": p["email"]}
                )
                ids[p["email"]] = str(row.scalar_one())

        print(f"  [auth] Seeded admin + {len(DOCTORS)} doctors + {len(PATIENTS)} patients.")
    finally:
        await engine.dispose()
    return ids
