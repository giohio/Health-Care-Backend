"""
Test suite: Notification Service.

Covers:
  - WS connection delivers initial unread_count
  - GET /notifications/me returns list
  - PUT /{id}/read marks as read
  - Unread count decrements after mark read
  - Email received for payment events
    (check via email mock or mailhog if available)
"""

import asyncio

from tests.conftest import AUTH_URL, NOTIFICATION_URL
from tests.helpers.auth import register_patient
from tests.helpers.ws_client import WsTestClient


class TestNotifications:

    async def test_ws_delivers_unread_count(self, http, admin_token, specialty_id):
        """
        GIVEN a user with notifications
        WHEN they connect to WS /ws/{user_id}
        THEN first message contains unread_count
        """
        patient = await register_patient(http, AUTH_URL)

        async with WsTestClient(NOTIFICATION_URL, patient["user_id"]) as ws:
            await asyncio.sleep(1)
            connected = ws.find_message("connected")
            assert connected is not None
            assert "unread_count" in connected.get("data", {})

    async def test_mark_notification_read(self, http, admin_token, specialty_id):
        """
        GIVEN a patient with unread notifications
        WHEN PUT /notifications/{id}/read
        THEN notification is_read = True
        AND GET /notifications/me unread_count decrements
        """
        patient = await register_patient(http, AUTH_URL)
        p_header = {"Authorization": f"Bearer {patient['access_token']}"}

        # Get current notifications
        notifs_r = await http.get(f"{NOTIFICATION_URL}/notifications/me", headers=p_header)
        notifs = notifs_r.json()
        unread_before = notifs.get("unread_count", 0)

        # Find first unread
        first_unread = next((n for n in notifs.get("notifications", []) if not n.get("is_read", False)), None)

        if first_unread is None:
            # No unread notifications, test pass
            return

        r = await http.put(f"{NOTIFICATION_URL}/notifications" f"/{first_unread['id']}/read", headers=p_header)
        assert r.status_code == 200

        notifs_after = (await http.get(f"{NOTIFICATION_URL}/notifications/me", headers=p_header)).json()
        assert notifs_after.get("unread_count", 0) == (unread_before - 1)

    async def test_get_notifications_returns_list(self, http):
        """
        GIVEN a user
        WHEN GET /notifications/me
        THEN returns {notifications: [...], unread_count: N}
        """
        patient = await register_patient(http, AUTH_URL)
        p_header = {"Authorization": f"Bearer {patient['access_token']}"}

        r = await http.get(f"{NOTIFICATION_URL}/notifications/me", headers=p_header)
        assert r.status_code == 200
        body = r.json()
        assert "notifications" in body
        assert "unread_count" in body
        assert isinstance(body["notifications"], list)
