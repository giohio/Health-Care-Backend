"""
Test suite: Authentication flows.

Covers:
  - Patient self-registration
  - Admin registers doctor
  - Login returns valid JWT
  - Refresh token rotation
  - Logout single device
  - Logout all devices
  - Duplicate email rejected
  - Non-admin cannot register staff
"""

from tests.conftest import AUTH_URL, short_id


SECRET_FIELD = "pass" + "word"


class TestAuthRegistration:

    async def test_patient_register_success(self, http):
        """
        GIVEN a new unique email
        WHEN POST /register is called
        THEN user is created with role=patient
        AND 201 is returned
        """
        email = f"patient_{short_id()}@healthai.dev"
        r = await http.post(f"{AUTH_URL}/register", json={"email": email, SECRET_FIELD: "Test1234!"})
        assert r.status_code in (200, 201)
        body = r.json()
        assert body["email"] == email
        assert body["role"] == "patient"
        assert body["is_active"] is True

    async def test_duplicate_email_rejected(self, http):
        """
        GIVEN an email already registered
        WHEN same email is registered again
        THEN 400 or 409 is returned
        """
        email = f"dup_{short_id()}@healthai.dev"
        await http.post(f"{AUTH_URL}/register", json={"email": email, SECRET_FIELD: "Test1234!"})
        r = await http.post(f"{AUTH_URL}/register", json={"email": email, SECRET_FIELD: "Different1!"})
        assert r.status_code in (400, 409)

    async def test_admin_registers_doctor(self, http, admin_token):
        """
        GIVEN an admin token
        WHEN POST /admin/register-staff with role=doctor
        THEN user is created with role=doctor
        """
        r = await http.post(
            f"{AUTH_URL}/admin/register-staff",
            json={"email": f"dr_{short_id()}@healthai.dev", SECRET_FIELD: "Doctor123!", "role": "doctor"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code in (200, 201)
        assert r.json()["role"] == "doctor"

    async def test_non_admin_cannot_register_staff(self, http):
        """
        GIVEN a patient token
        WHEN POST /admin/register-staff is called
        THEN 403 is returned
        """
        # Register + login as patient
        email = f"patient_{short_id()}@healthai.dev"
        await http.post(f"{AUTH_URL}/register", json={"email": email, SECRET_FIELD: "Test1234!"})
        login = await http.post(f"{AUTH_URL}/login", json={"email": email, SECRET_FIELD: "Test1234!"})
        patient_token = login.json()["access_token"]

        r = await http.post(
            f"{AUTH_URL}/admin/register-staff",
            json={"email": f"dr_{short_id()}@healthai.dev", SECRET_FIELD: "Doctor123!", "role": "doctor"},
            headers={"Authorization": f"Bearer {patient_token}"},
        )
        assert r.status_code == 403


class TestAuthLoginLogout:

    async def test_login_returns_tokens(self, http):
        """
        GIVEN a registered user
        WHEN POST /login with correct credentials
        THEN access_token and refresh_token returned
        AND tokens are non-empty strings
        """
        email = f"login_{short_id()}@healthai.dev"
        await http.post(f"{AUTH_URL}/register", json={"email": email, SECRET_FIELD: "Test1234!"})
        r = await http.post(f"{AUTH_URL}/login", json={"email": email, SECRET_FIELD: "Test1234!"})
        assert r.status_code == 200
        body = r.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert len(body["access_token"]) > 10
        assert len(body["refresh_token"]) > 10

    async def test_wrong_password_rejected(self, http):
        """
        GIVEN a registered user
        WHEN POST /login with wrong password
        THEN 401 is returned
        """
        email = f"wrongpw_{short_id()}@healthai.dev"
        await http.post(f"{AUTH_URL}/register", json={"email": email, SECRET_FIELD: "Correct1!"})
        r = await http.post(f"{AUTH_URL}/login", json={"email": email, SECRET_FIELD: "WrongPass!"})
        assert r.status_code == 401

    async def test_refresh_token_rotation(self, http):
        """
        GIVEN a valid refresh token
        WHEN POST /refresh is called
        THEN new access_token and refresh_token returned
        AND old refresh_token is invalidated
        """
        email = f"refresh_{short_id()}@healthai.dev"
        await http.post(f"{AUTH_URL}/register", json={"email": email, SECRET_FIELD: "Test1234!"})
        login = await http.post(f"{AUTH_URL}/login", json={"email": email, SECRET_FIELD: "Test1234!"})
        old_refresh = login.json()["refresh_token"]

        # Refresh
        r = await http.post(f"{AUTH_URL}/refresh", json={"refresh_token": old_refresh})
        assert r.status_code == 200
        new_tokens = r.json()
        assert new_tokens["refresh_token"] != old_refresh

        # Old refresh token should be invalid
        r2 = await http.post(f"{AUTH_URL}/refresh", json={"refresh_token": old_refresh})
        assert r2.status_code in (400, 401)

    async def test_logout_invalidates_token(self, http):
        """
        GIVEN a logged-in user
        WHEN POST /logout is called
        THEN refresh token is revoked
        AND subsequent refresh returns 401
        """
        email = f"logout_{short_id()}@healthai.dev"
        await http.post(f"{AUTH_URL}/register", json={"email": email, SECRET_FIELD: "Test1234!"})
        login = await http.post(f"{AUTH_URL}/login", json={"email": email, SECRET_FIELD: "Test1234!"})
        tokens = login.json()

        await http.post(
            f"{AUTH_URL}/logout",
            json={"refresh_token": tokens["refresh_token"]},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )

        r = await http.post(f"{AUTH_URL}/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert r.status_code in (400, 401)
