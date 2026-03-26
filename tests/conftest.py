"""
Shared fixtures for all E2E tests.

Naming convention for test accounts:
    patient:  test_patient_{uuid_short}@healthai.dev
    doctor:   test_doctor_{uuid_short}@healthai.dev
    admin:    test_admin_{uuid_short}@healthai.dev

All test accounts are created fresh per test session.
No shared state between test files.
"""

import asyncio
import base64
import json
import os
import subprocess
import uuid
from pathlib import Path

import httpx
import pytest
from _pytest.outcomes import Exit
from dotenv import load_dotenv

load_dotenv(".env.test")

AUTH_URL = os.getenv("AUTH_URL")
PATIENT_URL = os.getenv("PATIENT_URL")
DOCTOR_URL = os.getenv("DOCTOR_URL")
APPOINTMENT_URL = os.getenv("APPOINTMENT_URL")
NOTIFICATION_URL = os.getenv("NOTIFICATION_URL")
PAYMENT_URL = os.getenv("PAYMENT_URL")
EVENT_TIMEOUT = int(os.getenv("EVENT_PROPAGATION_TIMEOUT", "10"))


def short_id() -> str:
    return str(uuid.uuid4())[:8]


@pytest.fixture(scope="session")
async def http():
    """Shared AsyncClient for all tests."""
    timeout = httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0)
    limits = httpx.Limits(max_connections=100, max_keepalive_connections=0)
    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        yield client


async def _wait_for_auth_ready(http: httpx.AsyncClient, timeout_seconds: int = 45) -> None:
    """Wait until Auth endpoint behind gateway responds and points to the correct upstream."""
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    last_error = None

    while asyncio.get_running_loop().time() < deadline:
        try:
            resp = await http.get(f"{AUTH_URL}/health")
            if resp.status_code == 200:
                openapi_resp = await http.get(f"{AUTH_URL}/openapi.json")
                if openapi_resp.status_code == 200:
                    spec = openapi_resp.json()
                    title = str(spec.get("info", {}).get("title", ""))
                    paths = spec.get("paths", {})
                    has_login_post = "post" in paths.get("/login", {})
                    has_register_post = "post" in paths.get("/register", {})

                    if "Auth" in title and has_login_post and has_register_post:
                        return

                    last_error = (
                        "AUTH_URL is reachable but not mapped to Auth Service. "
                        f"title={title!r}, has_login_post={has_login_post}, "
                        f"has_register_post={has_register_post}"
                    )
                else:
                    last_error = f"openapi status={openapi_resp.status_code}, body={openapi_resp.text}"
            else:
                last_error = f"status={resp.status_code}, body={resp.text}"
        except Exception as exc:
            last_error = str(exc)

        await asyncio.sleep(1)

    pytest.exit(
        "Auth service is not reachable via gateway. "
        f"Last error: {last_error}. "
        "Check `docker compose ps` and `docker compose logs kong auth_service`.",
        returncode=2,
    )


async def _wait_for_service_ready(
    http: httpx.AsyncClient,
    base_url: str | None,
    service_name: str,
    timeout_seconds: int = 60,
) -> None:
    """Wait until a service endpoint is reachable through gateway."""
    if not base_url:
        pytest.exit(f"Missing service URL for {service_name} in .env.test", returncode=2)

    deadline = asyncio.get_running_loop().time() + timeout_seconds
    last_error = None
    while asyncio.get_running_loop().time() < deadline:
        try:
            resp = await http.get(f"{base_url}/health")
            if resp.status_code < 500:
                return
            last_error = f"status={resp.status_code}, body={resp.text}"
        except Exception as exc:
            last_error = str(exc)
        await asyncio.sleep(1)

    pytest.exit(
        f"{service_name} is not reachable via gateway. Last error: {last_error}",
        returncode=2,
    )


def _deref_openapi_schema(spec: dict, schema: dict) -> dict:
    if not isinstance(schema, dict):
        return {}
    ref = schema.get("$ref")
    if not ref or not isinstance(ref, str):
        return schema
    if not ref.startswith("#/components/schemas/"):
        return schema
    schema_name = ref.split("/")[-1]
    return spec.get("components", {}).get("schemas", {}).get(schema_name, {})


def _notification_me_is_object_contract(spec: dict) -> bool:
    paths = spec.get("paths", {})
    operation = paths.get("/notifications/me", {}).get("get") or paths.get("/me", {}).get("get")
    if not operation:
        return False

    schema = (
        operation.get("responses", {}).get("200", {}).get("content", {}).get("application/json", {}).get("schema", {})
    )
    resolved = _deref_openapi_schema(spec, schema)

    if resolved.get("type") == "object":
        return True

    properties = resolved.get("properties", {}) if isinstance(resolved, dict) else {}
    return "notifications" in properties and "unread_count" in properties


def _contract_debug_hint(spec: dict) -> str:
    info_title = str(spec.get("info", {}).get("title", ""))
    sample_paths = list(spec.get("paths", {}).keys())[:5]
    return f"detected_title={info_title!r}, sample_paths={sample_paths}"


async def _validate_service_contract(
    http: httpx.AsyncClient,
    base_url: str | None,
    service_name: str,
    predicate,
    contract_error: str,
) -> None:
    await _wait_for_service_ready(http, base_url, service_name, timeout_seconds=90)
    try:
        openapi_resp = await http.get(f"{base_url}/openapi.json")
        if openapi_resp.status_code != 200:
            pytest.exit(
                f"{service_name} openapi is not reachable. status={openapi_resp.status_code}",
                returncode=2,
            )

        spec = openapi_resp.json()
        if not predicate(spec):
            pytest.exit(
                f"{service_name} runtime contract mismatch: {contract_error}. "
                f"Likely stale container image or wrong gateway route. {_contract_debug_hint(spec)}",
                returncode=2,
            )
    except Exit:
        raise
    except Exception as exc:
        pytest.exit(
            f"Failed to validate {service_name} runtime contract: {exc}",
            returncode=2,
        )


async def _assert_runtime_contracts(http: httpx.AsyncClient) -> None:
    """Fail fast when runtime contracts do not match what E2E suite expects."""

    checks = [
        (
            APPOINTMENT_URL,
            "appointment_service",
            lambda spec: "get" in spec.get("paths", {}).get("/{appointment_id}", {}),
            "missing GET /{appointment_id}",
        ),
        (
            NOTIFICATION_URL,
            "notification_service",
            _notification_me_is_object_contract,
            "GET /notifications/me response is not object contract",
        ),
        (
            PAYMENT_URL,
            "payment_service",
            lambda spec: "get" in spec.get("paths", {}).get("/payments/{appointment_id}", {}),
            "missing GET /payments/{appointment_id}",
        ),
    ]

    for base_url, service_name, predicate, contract_error in checks:
        await _validate_service_contract(http, base_url, service_name, predicate, contract_error)


def _seed_admin_account() -> tuple[bool, str]:
    """Run seed script once to provision default admin credentials for tests."""
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "seed_admin.py"
    if not script_path.exists():
        return False, f"Missing seed script: {script_path}"

    result = subprocess.run(
        [os.sys.executable, str(script_path)],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return True, result.stdout
    return False, (result.stdout + "\n" + result.stderr).strip()


def _jwt_role(access_token: str | None) -> str | None:
    if not access_token:
        return None
    try:
        parts = access_token.split(".")
        if len(parts) < 2:
            return None
        payload = parts[1]
        payload += "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8")
        data = json.loads(decoded)
        role = data.get("role")
        return role.lower() if isinstance(role, str) else None
    except Exception:
        return None


def _admin_env_credentials() -> tuple[str, str]:
    email = os.getenv("ADMIN_EMAIL") or "admin@healthai.dev"
    secret = os.getenv("ADMIN_PASSWORD")
    if not secret:
        raise AssertionError("Missing ADMIN_PASSWORD in environment for E2E tests")
    return email, secret


async def _admin_login(http: httpx.AsyncClient, email: str, secret: str) -> httpx.Response:
    return await http.post(
        f"{AUTH_URL}/login",
        json={"email": email, "password": secret},
    )


async def _login_with_optional_seed(http: httpx.AsyncClient, email: str, secret: str) -> httpx.Response:
    seeded = False
    last_response = None

    for _ in range(10):
        r = await _admin_login(http, email, secret)
        last_response = r
        if r.status_code == 200:
            return r

        if r.status_code == 401 and not seeded:
            ok, output = _seed_admin_account()
            seeded = True
            if not ok:
                raise AssertionError(
                    "Admin login failed and seed script did not complete successfully.\n" f"seed output: {output}"
                )
            r = await _admin_login(http, email, secret)
            last_response = r
            if r.status_code == 200:
                return r

        await asyncio.sleep(1)

    raise AssertionError(
        "Admin login failed after retries. "
        f"status={last_response.status_code if last_response else 'N/A'}, "
        f"body={last_response.text if last_response else 'N/A'}. "
        "Run: python scripts/seed_admin.py and verify docker stack is healthy."
    )


@pytest.fixture(scope="session", autouse=True)
async def ensure_stack_ready(http):
    """Preflight stack check to avoid cascading failures across the suite."""
    await _wait_for_auth_ready(http)
    await _assert_runtime_contracts(http)


@pytest.fixture(scope="session")
async def admin_token(http):
    """
    Login as admin. Admin account must exist
    in DB before running tests.
    Seed: INSERT INTO users (email, role...)
    or run: python scripts/seed_admin.py
    """
    email, secret = _admin_env_credentials()
    last_response = await _login_with_optional_seed(http, email, secret)

    access_token = last_response.json()["access_token"]
    if _jwt_role(access_token) != "admin":
        ok, output = _seed_admin_account()
        if not ok:
            raise AssertionError(
                "Logged-in admin user does not have admin role and reseed failed.\n" f"seed output: {output}"
            )
        r = await _admin_login(http, email, secret)
        assert r.status_code == 200, f"Admin re-login failed after reseed: {r.text}"
        access_token = r.json()["access_token"]
        assert _jwt_role(access_token) == "admin", "Token role is not admin after reseed"

    return access_token


@pytest.fixture(scope="session")
async def specialty_id(http, admin_token):
    """Create a test specialty once per session."""
    await _wait_for_service_ready(http, DOCTOR_URL, "doctor_service", timeout_seconds=90)

    payload = {"name": f"General Medicine {short_id()}"}
    headers = {"Authorization": f"Bearer {admin_token}"}

    last_status = None
    last_body = None
    for _ in range(20):
        try:
            r = await http.post(f"{DOCTOR_URL}/specialties", json=payload, headers=headers)
            last_status = r.status_code
            last_body = r.text
            if r.status_code in (200, 201):
                return r.json()["id"]
        except httpx.HTTPError as exc:
            last_body = str(exc)

        await asyncio.sleep(1)

    raise AssertionError(
        "Failed to create specialty for doctor tests. " f"last_status={last_status}, last_body={last_body}"
    )
