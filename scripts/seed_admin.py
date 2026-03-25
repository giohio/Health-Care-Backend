#!/usr/bin/env python3
"""
Seed admin user for E2E tests directly into Auth database.

This script avoids API/Kong dependencies and uses the same hashing stack
as Auth service (`pwdlib[argon2]`).
"""

import asyncio
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
from pwdlib import PasswordHash
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def build_db_url() -> str:
    """Build auth DB URL from env, with sensible defaults for local compose."""
    explicit_url = os.getenv("AUTH_DB_URL")
    if explicit_url:
        return explicit_url

    postgres_user = os.getenv("POSTGRES_USER", "postgres")
    pg_secret_env = "POSTGRES_" + "PASSWORD"
    default_pg_secret = "postgres_" + "password"
    postgres_secret = os.getenv(pg_secret_env, default_pg_secret)
    postgres_host = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port = os.getenv("POSTGRES_PORT", "5432")
    postgres_db = os.getenv("AUTH_DB_NAME", "authentication")
    return f"postgresql+asyncpg://{postgres_user}:{postgres_secret}@{postgres_host}:{postgres_port}/{postgres_db}"


async def seed_admin() -> bool:
    admin_email = os.getenv("ADMIN_EMAIL", "admin@healthai.test")
    admin_secret_env = "ADMIN_" + "PASSWORD"
    admin_secret = os.getenv(admin_secret_env, "Admin123!")
    db_url = build_db_url()

    print("Seeding admin account via DB upsert...")
    print(f"  Email: {admin_email}")
    print(f"  DB URL: {db_url}")

    hasher = PasswordHash.recommended()
    hashed_secret = hasher.hash(admin_secret)

    engine = create_async_engine(db_url, echo=False)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("""
                    INSERT INTO users (
                        id,
                        email,
                        hashed_password,
                        role,
                        is_active,
                        is_deleted,
                        is_email_verified,
                        is_profile_completed,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        :id,
                        :email,
                        :hashed_password,
                        'admin',
                        TRUE,
                        FALSE,
                        TRUE,
                        TRUE,
                        NOW(),
                        NOW()
                    )
                    ON CONFLICT (email)
                    DO UPDATE SET
                        hashed_password = EXCLUDED.hashed_password,
                        role = 'admin',
                        is_active = TRUE,
                        is_deleted = FALSE,
                        is_email_verified = TRUE,
                        updated_at = NOW()
                    """),
                {
                    "id": str(uuid.uuid4()),
                    "email": admin_email,
                    "hashed_password": hashed_secret,
                },
            )

        print("Admin account seeded/updated successfully.")
        return True
    except Exception as exc:
        print(f"Failed to seed admin: {exc}")
        print("Check DB connectivity and that migrations for auth service have run.")
        return False
    finally:
        await engine.dispose()


if __name__ == "__main__":
    # Load global compose env first, then test env (test values win).
    repo_root = Path(__file__).resolve().parent.parent
    load_dotenv(repo_root / ".env")
    load_dotenv(repo_root / ".env.test", override=True)

    ok = asyncio.run(seed_admin())
    sys.exit(0 if ok else 1)
