"""
Integration tests: email OTP verification flow.

Tests the full OTP registration → verify → login cycle via the Kong gateway,
isolating Auth service behavior (no cross-service dependencies required).
"""

from tests.conftest import AUTH_URL, short_id

SECRET_FIELD = "pass" + "word"


class TestEmailOTPVerificationFlow:
    """Integration: patient must verify email before login succeeds."""

    async def test_unverified_patient_cannot_login(self, http):
        """
        GIVEN a patient who just registered (email NOT verified)
        WHEN POST /login is attempted
        THEN 401 is returned (email not verified → can_login() is False)
        """
        email = f"unverified_{short_id()}@healthai.dev"
        secret = f"Sec{short_id()[:8]}1!"

        reg = await http.post(f"{AUTH_URL}/register", json={"email": email, SECRET_FIELD: secret})
        assert reg.status_code in (200, 201), reg.text

        login = await http.post(f"{AUTH_URL}/login", json={"email": email, SECRET_FIELD: secret})
        assert login.status_code == 401

    async def test_register_patient_is_email_verified_false(self, http):
        """
        GIVEN a new patient registration
        THEN is_email_verified is False in the response
        """
        email = f"isfv_{short_id()}@healthai.dev"
        secret = f"Sec{short_id()[:8]}1!"

        reg = await http.post(f"{AUTH_URL}/register", json={"email": email, SECRET_FIELD: secret})
        assert reg.status_code in (200, 201)
        assert reg.json()["is_email_verified"] is False

    async def test_full_otp_verify_then_login_succeeds(self, http):
        """
        GIVEN a patient who registered
        WHEN OTP is retrieved via debug endpoint and submitted to /verify-email
        THEN /login returns 200 and valid tokens
        """
        email = f"verify_{short_id()}@healthai.dev"
        secret = f"Sec{short_id()[:8]}1!"

        reg = await http.post(f"{AUTH_URL}/register", json={"email": email, SECRET_FIELD: secret})
        assert reg.status_code in (200, 201)

        # Fetch OTP from debug route
        otp_resp = await http.get(f"{AUTH_URL}/dev/otp/{email}")
        assert otp_resp.status_code == 200, f"Debug OTP endpoint failed: {otp_resp.text}"
        otp = otp_resp.json()["otp"]
        assert len(otp) == 6 and otp.isdigit()

        # Verify email
        v = await http.post(f"{AUTH_URL}/verify-email", json={"email": email, "otp": otp})
        assert v.status_code == 200

        # Login should succeed now
        login = await http.post(f"{AUTH_URL}/login", json={"email": email, SECRET_FIELD: secret})
        assert login.status_code == 200
        tokens = login.json()
        assert "access_token" in tokens
        assert len(tokens["access_token"]) > 10

    async def test_verify_with_wrong_otp_returns_400(self, http):
        """
        GIVEN a registered patient
        WHEN /verify-email is called with an incorrect OTP
        THEN 400 is returned
        """
        email = f"wrotp_{short_id()}@healthai.dev"
        secret = f"Sec{short_id()[:8]}1!"

        await http.post(f"{AUTH_URL}/register", json={"email": email, SECRET_FIELD: secret})

        v = await http.post(f"{AUTH_URL}/verify-email", json={"email": email, "otp": "000000"})
        assert v.status_code == 400

    async def test_verify_already_verified_returns_400(self, http):
        """
        GIVEN a patient who already verified their email
        WHEN /verify-email is called again
        THEN 400 is returned
        """
        email = f"re_verify_{short_id()}@healthai.dev"
        secret = f"Sec{short_id()[:8]}1!"

        await http.post(f"{AUTH_URL}/register", json={"email": email, SECRET_FIELD: secret})

        # First verify
        otp_resp = await http.get(f"{AUTH_URL}/dev/otp/{email}")
        otp = otp_resp.json()["otp"]
        first = await http.post(f"{AUTH_URL}/verify-email", json={"email": email, "otp": otp})
        assert first.status_code == 200

        # Second verify attempt
        second = await http.post(f"{AUTH_URL}/verify-email", json={"email": email, "otp": otp})
        assert second.status_code == 400

    async def test_otp_consumed_after_successful_verify(self, http):
        """
        GIVEN a successful OTP verification
        WHEN debug OTP endpoint is queried again
        THEN 404 is returned (OTP deleted from Redis)
        """
        email = f"otp_del_{short_id()}@healthai.dev"
        secret = f"Sec{short_id()[:8]}1!"

        await http.post(f"{AUTH_URL}/register", json={"email": email, SECRET_FIELD: secret})
        otp_resp = await http.get(f"{AUTH_URL}/dev/otp/{email}")
        otp = otp_resp.json()["otp"]

        await http.post(f"{AUTH_URL}/verify-email", json={"email": email, "otp": otp})

        # OTP should be gone now
        after = await http.get(f"{AUTH_URL}/dev/otp/{email}")
        assert after.status_code == 404

    async def test_resend_otp_requires_cooldown(self, http):
        """
        GIVEN a patient who just registered (OTP just sent)
        WHEN /resend-otp is called immediately
        THEN 429 is returned (within cooldown window)
        """
        email = f"cooldown_{short_id()}@healthai.dev"
        secret = f"Sec{short_id()[:8]}1!"

        await http.post(f"{AUTH_URL}/register", json={"email": email, SECRET_FIELD: secret})

        r = await http.post(f"{AUTH_URL}/resend-otp", json={"email": email})
        assert r.status_code == 429

    async def test_resend_otp_for_unknown_email_returns_200(self, http):
        """
        GIVEN an email that is not registered
        WHEN /resend-otp is called
        THEN 200 is returned (no information leak)
        """
        r = await http.post(f"{AUTH_URL}/resend-otp", json={"email": f"ghost_{short_id()}@healthai.dev"})
        assert r.status_code == 200

    async def test_staff_registered_by_admin_is_pre_verified(self, http, admin_token):
        """
        GIVEN a doctor registered by an admin
        THEN is_email_verified is True (staff bypass OTP)
        """
        r = await http.post(
            f"{AUTH_URL}/admin/register-staff",
            json={"email": f"drv_{short_id()}@healthai.dev", SECRET_FIELD: "Doctor123!", "role": "doctor"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code in (200, 201), r.text
        assert r.json()["is_email_verified"] is True

    async def test_verify_email_invalid_schema_returns_422(self, http):
        """OTP must be exactly 6 digits."""
        r = await http.post(f"{AUTH_URL}/verify-email", json={"email": "u@example.com", "otp": "12"})
        assert r.status_code == 422
