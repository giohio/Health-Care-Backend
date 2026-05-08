import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Common passwords found in .env files
PASSWORDS = ["12345678", "postgres", "postgres_password"]

async def try_connect(db_name, passwords):
    for pwd in passwords:
        url = f"postgresql+asyncpg://postgres:{pwd}@localhost:5432/{db_name}"
        engine = create_async_engine(url)
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                print(f"Connected to {db_name} with password {pwd}")
                return engine
        except Exception:
            await engine.dispose()
    print(f"Failed to connect to {db_name}")
    return None

async def sync_names():
    print("Starting sync...")
    auth_engine = await try_connect("authentication", PASSWORDS)
    doctor_engine = await try_connect("doctor_db", PASSWORDS)
    patient_engine = await try_connect("patient_db", PASSWORDS)

    if not auth_engine:
        print("Fatal: Could not connect to Auth database.")
        return

    names = {} # user_id -> full_name

    # Fetch doctor names
    if doctor_engine:
        try:
            async with doctor_engine.connect() as conn:
                res = await conn.execute(text("SELECT user_id, full_name FROM doctors"))
                for row in res.fetchall():
                    if row[1]: names[str(row[0])] = row[1]
        except Exception as e:
            print(f"Error fetching doctors: {e}")
    
    # Fetch patient names
    if patient_engine:
        try:
            async with patient_engine.connect() as conn:
                # Updated table name to patient_profiles
                res = await conn.execute(text("SELECT user_id, full_name FROM patient_profiles"))
                for row in res.fetchall():
                    if row[1]: names[str(row[0])] = row[1]
        except Exception as e:
            print(f"Error fetching patients: {e}")
    
    print(f"Collected {len(names)} names from other services.")

    # Update Auth Service
    try:
        async with auth_engine.begin() as conn:
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR(255)"))
            
            count = 0
            for user_id, name in names.items():
                res = await conn.execute(
                    text("UPDATE users SET full_name = :name WHERE id = :id AND (full_name IS NULL OR full_name = '')"),
                    {"name": name, "id": user_id}
                )
                if res.rowcount > 0:
                    count += 1
            print(f"Successfully synced {count} names to Auth database.")
    except Exception as e:
        print(f"Error updating Auth: {e}")

    await auth_engine.dispose()
    if doctor_engine: await doctor_engine.dispose()
    if patient_engine: await patient_engine.dispose()

if __name__ == "__main__":
    asyncio.run(sync_names())
