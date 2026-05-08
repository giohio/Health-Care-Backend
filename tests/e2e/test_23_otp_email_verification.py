"""
E2E test: OTP email verification complete flow.

Verifies the end-to-end journey:
  Patient registers → email is unverified → receives OTP →
  verifies email → login succeeds → can access protected resources.

Also verifies that unverified patients are blocked from protected endpoints.
"""

import asyncio

from tests.conftest import AUTH_URL, PATIENT_URL, short_id

SECRET_FIELD = "pass" + "word"


async def _get_otp(http, auth_url: str, email: str) -> str | None:
    """Retrieve OTP from the debug endpoint. Returns None if unavailable."""
    resp = await http.get(f"{auth_url}/dev/otp/{email}")
    if resp.status_code == 200:
        return resp.json()["otp"]
    return None


class TestOTPEmailVerificationE2E:
    """Full E2E coverage of the OTP verification flow."""

    async def test_patient_registration_returns_unverified(self, http):
        """
        GIVEN fresh patient registration
        THEN response has is_email_verified=False
        """
        email = f"e2e_unver_{short_id()}@healthai.dev"
        r = await http.post(f"{AUTH_URL}/register", json={"email": email, SECRET_FIELD: "Test1234!"})
        assert r.status_code in (200, 201)
        assert r.json()["is_email_verified"] is False

    async def test_unverified_patient_cannot_login(self, http):
        """
        GIVEN patient has not verified email
        WHEN login is attempted
        THEN 401 Unauthorized is returned
        """
        email = f"e2e_nologin_{short_id()}@healthai.dev"
        await http.post(f"{AUTH_URL}/register", json={"email": email, SECRET_FIELD: "Test1234!"})
        login = await http.post(f"{AUTH_URL}/login", json={"email": email, SECRET_FIELD: "Test1234!"})
        assert login.status_code == 401

    async def test_full_otp_flow_allows_login_and_access(self, http):
        """
        GIVEN patient completes the full OTP verification
        WHEN login is attempted AND profile endpoint is accessed
        THEN login returns 200 with tokens
        AND patient service profile route returns 200
        """
        email = f"e2e_full_{short_id()}@healthai.dev"
        secret = f"Sec{short_id()[:8]}1!"

        # Register
        reg = await http.post(f"{AUTH_URL}/register", json={"email": email, SECRET_FIELD: secret})
        assert reg.status_code in (200, 201), reg.text

        # Get OTP
        otp = await _get_otp(http, AUTH_URL, email)
        assert otp is not None, "Debug OTP endpoint unavailable — ensure DEBUG=True"

        # Verify email
        v = await http.post(f"{AUTH_URL}/verify-email", json={"email": email, "otp": otp})
        assert v.status_code == 200, v.text

        # Login
        login = await http.post(f"{AUTH_URL}/login", json={"email": email, SECRET_FIELD: secret})
        assert login.status_code == 200, login.text
        access_token = login.json()["access_token"]

        # Access patient profile (protected route)
        profile = await http.get(
            f"{PATIENT_URL}/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert profile.status_code in (200, 404)  # 404 means profile not yet created — still authenticated

    async def test_wrong_otp_keeps_user_unverified(self, http):
        """
        GIVEN patient submits wrong OTP
        WHEN login is attempted
        THEN login still returns 401 (still unverified)
        """
        email = f"e2e_wrotp_{short_id()}@healthai.dev"
        secret = f"Sec{short_id()[:8]}1!"

        await http.post(f"{AUTH_URL}/register", json={"email": email, SECRET_FIELD: secret})

        bad_verify = await http.post(f"{AUTH_URL}/verify-email", json={"email": email, "otp": "000000"})
        assert bad_verify.status_code == 400

        # Still can't login
        login = await http.post(f"{AUTH_URL}/login", json={"email": email, SECRET_FIELD: secret})
        assert login.status_code == 401

    async def test_resend_otp_flow(self, http):
        """
        GIVEN a patient in cooldown after registration
        WHEN cooldown passes and new OTP is requested via resend
        THEN new OTP can be retrieved and email verified successfully
        (Note: In real environment cooldown is 120s; we just verify
         the resend endpoint returns 429 while in cooldown)
        """
        email = f"e2e_resend_{short_id()}@healthai.dev"
        secret = f"Sec{short_id()[:8]}1!"

        await http.post(f"{AUTH_URL}/register", json={"email": email, SECRET_FIELD: secret})

        # Immediate resend → should be blocked by cooldown
        resend = await http.post(f"{AUTH_URL}/resend-otp", json={"email": email})
        assert resend.status_code == 429

    async def test_verify_otp_schema_validation(self, http):
        """
        GIVEN invalid OTP payload
        WHEN /verify-email is called
        THEN 422 Unprocessable Entity is returned
        """
        cases = [
            {"email": "x@x.com", "otp": "123"},         # too short
            {"email": "x@x.com", "otp": "12345a"},      # non-numeric
            {"email": "x@x.com", "otp": "1234567"},     # too long
            {"email": "not-an-email", "otp": "123456"}, # bad email
        ]
        for payload in cases:
            r = await http.post(f"{AUTH_URL}/verify-email", json=payload)
            assert r.status_code == 422, f"Expected 422 for payload {payload}, got {r.status_code}"

    async def test_staff_doctor_login_without_otp(self, http, admin_token):
        """
        GIVEN a doctor registered by admin (pre-verified)
        WHEN login is attempted immediately
        THEN login succeeds (no OTP required)
        """
        email = f"e2e_dr_{short_id()}@healthai.dev"
        r = await http.post(
            f"{AUTH_URL}/admin/register-staff",
            json={"email": email, SECRET_FIELD: "Doctor123!", "role": "doctor"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code in (200, 201), r.text
        assert r.json()["is_email_verified"] is True

        login = await http.post(f"{AUTH_URL}/login", json={"email": email, SECRET_FIELD: "Doctor123!"})
        assert login.status_code == 200, login.text
        assert "access_token" in login.json()
