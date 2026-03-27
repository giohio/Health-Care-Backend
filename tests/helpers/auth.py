"""Helper functions for auth operations."""

import asyncio
import os

import httpx


def _new_test_secret(prefix: str) -> str:
    """Generate deterministic-enough secret for test users without hardcoded literals."""
    from tests.conftest import short_id

    # Auth service enforces max length 20, keep generated secret compact.
    compact_prefix = "pt" if prefix.startswith("patient") else "dr"
    return f"{compact_prefix}{short_id()[:10]}Aa1!"


async def register_patient(http: httpx.AsyncClient, auth_url: str) -> dict:
    """Register a new patient and return credentials."""
    from tests.conftest import short_id

    email = f"patient_{short_id()}@healthai.dev"
    secret = _new_test_secret("patient")

    # Surgical cookie deletion to prevent role collisions in Kong
    if "access_token" in http.cookies:
        del http.cookies["access_token"]

    r = await http.post(
        f"{auth_url}/register",
        json={
            "email": email,
            "password": secret,
        },
    )
    assert r.status_code in (200, 201), f"Patient register failed: {r.text}"
    user = r.json()

    # Login to get token
    r2 = await http.post(f"{auth_url}/login", json={"email": email, "password": secret})
    assert r2.status_code == 200, f"Login failed with {r2.status_code}: {r2.text}"
    token_data = r2.json()

    return {
        "user_id": user["id"],
        "email": email,
        "password": secret,
        "access_token": token_data["access_token"],
        "refresh_token": token_data["refresh_token"],
    }


async def register_doctor(
    http: httpx.AsyncClient,
    auth_url: str,
    doctor_url: str,
    admin_token: str,
    specialty_id: str,
) -> dict:
    """
    Register a doctor via admin endpoint.
    Then update profile with specialty.
    """
    from tests.conftest import short_id

    email = f"doctor_{short_id()}@healthai.dev"
    secret = _new_test_secret("doctor")

    # Surgical cookie deletion to prevent role collisions in Kong
    if "access_token" in http.cookies:
        del http.cookies["access_token"]

    # Refresh admin token to avoid stale/expired session-scoped token during long E2E runs.
    admin_email = os.getenv("ADMIN_EMAIL") or "admin@healthai.dev"
    admin_secret = os.getenv("ADMIN_PASSWORD")
    if not admin_secret:
        raise AssertionError("Missing ADMIN_PASSWORD in environment for E2E tests")
    fresh_admin_token = admin_token
    admin_login = await http.post(
        f"{auth_url}/login",
        json={"email": admin_email, "password": admin_secret},
    )
    if admin_login.status_code == 200:
        fresh_admin_token = admin_login.json().get("access_token", admin_token)

    # Create doctor account via admin
    r = await http.post(
        f"{auth_url}/admin/register-staff",
        json={"email": email, "password": secret, "role": "doctor"},
        headers={
            "Authorization": f"Bearer {fresh_admin_token}",
            "X-User-Role": "admin",
        },
    )
    assert r.status_code in (200, 201), f"Doctor register failed: {r.text}"
    user = r.json()

    # Ensure doctor aggregate exists in Doctor service without waiting for async event consumer.
    full_name = f"Dr. Test {short_id()}"
    provision_resp = await http.post(
        f"{doctor_url}/",
        json={
            "user_id": user["id"],
            "full_name": full_name,
        },
        headers={
            "Authorization": f"Bearer {fresh_admin_token}",
            "X-User-Role": "admin",
        },
    )
    assert provision_resp.status_code in (200, 201), f"Doctor provision failed: {provision_resp.text}"

    # Login
    r2 = await http.post(f"{auth_url}/login", json={"email": email, "password": secret})
    assert r2.status_code == 200
    token_data = r2.json()
    doctor_token = token_data["access_token"]

    # Wait for user.registered consumer to materialize doctor profile before update.
    update_payload = {
        "user_id": user["id"],
        "full_name": full_name,
        "title": "Dr.",
        "specialty_id": specialty_id,
        "experience_years": 5,
    }
    r3 = None
    for _ in range(20):
        r3 = await http.put(
            f"{doctor_url}/{user['id']}", json=update_payload, headers={"Authorization": f"Bearer {doctor_token}"}
        )
        if r3.status_code == 200:
            break
        await asyncio.sleep(0.5)

    assert r3 is not None and r3.status_code == 200, f"Doctor profile update failed: {r3.text if r3 else 'no response'}"

    return {
        "user_id": user["id"],
        "email": email,
        "access_token": doctor_token,
    }


async def add_doctor_schedule(
    http: httpx.AsyncClient,
    doctor_url: str,
    doctor_id: str,
    doctor_token: str,
) -> None:
    """
    Set doctor working schedule for all weekdays.
    08:00 - 17:00, 20-minute slots.
    """
    days = [0, 1, 2, 3, 4]
    r = await http.put(
        f"{doctor_url}/{doctor_id}/schedule",
        json=[
            {
                "doctor_id": doctor_id,
                "day_of_week": day,
                "start_time": "08:00",
                "end_time": "17:00",
                "slot_duration_minutes": 20,
            }
            for day in days
        ],
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert r.status_code == 200, f"Set schedule failed: {r.text}"
