"""
Unit tests for Notification Service AuthServiceClient.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from infrastructure.clients.auth_service_client import AuthServiceClient


# ──────────────────────────────────────────────
# Shared helpers matching test_notification_consumers.py pattern
# ──────────────────────────────────────────────

class FakeSession:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        await asyncio.sleep(0)
        self.commits += 1


class SessionFactory:
    def __call__(self):
        return self

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def __init__(self):
        self.session = FakeSession()


class FakeCreateNotificationUC:
    def __init__(self, sink):
        self.sink = sink

    async def execute(self, **kwargs):
        await asyncio.sleep(0)
        self.sink.append(kwargs)


def _factory(sink):
    return lambda _session: FakeCreateNotificationUC(sink)


# ──────────────────────────────────────────────
# AuthServiceClient unit tests
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_user_email_success():
    """Returns email when auth service responds 200."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "u-1", "email": "user@example.com"}

    client = AuthServiceClient("http://auth_service:8000")
    with patch.object(client.client, "get", new_callable=AsyncMock, return_value=mock_resp):
        email = await client.get_user_email("u-1")

    assert email == "user@example.com"


@pytest.mark.asyncio
async def test_get_user_email_not_found_returns_none():
    """Returns None when auth service responds 404."""
    mock_resp = MagicMock()
    mock_resp.status_code = 404

    client = AuthServiceClient("http://auth_service:8000")
    with patch.object(client.client, "get", new_callable=AsyncMock, return_value=mock_resp):
        email = await client.get_user_email("missing-id")

    assert email is None


@pytest.mark.asyncio
async def test_get_user_email_network_error_returns_none():
    """Returns None when a network error occurs — does not propagate exception."""
    client = AuthServiceClient("http://auth_service:8000")
    with patch.object(client.client, "get", new_callable=AsyncMock, side_effect=Exception("connection refused")):
        email = await client.get_user_email("u-1")

    assert email is None


@pytest.mark.asyncio
async def test_get_user_email_missing_email_field_returns_none():
    """Returns None when response is 200 but 'email' key is absent."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "u-1"}  # no 'email' key

    client = AuthServiceClient("http://auth_service:8000")
    with patch.object(client.client, "get", new_callable=AsyncMock, return_value=mock_resp):
        email = await client.get_user_email("u-1")

    assert email is None


@pytest.mark.asyncio
async def test_get_user_email_500_returns_none():
    """Returns None for any non-200 status."""
    mock_resp = MagicMock()
    mock_resp.status_code = 500

    client = AuthServiceClient("http://auth_service:8000")
    with patch.object(client.client, "get", new_callable=AsyncMock, return_value=mock_resp):
        email = await client.get_user_email("u-1")

    assert email is None


def test_constructor_default_base_url():
    """Default base_url is auth_service:8000."""
    client = AuthServiceClient()
    assert "auth_service" in client.base_url


def test_constructor_custom_base_url():
    """Custom base_url is stored on the instance."""
    client = AuthServiceClient("http://custom-auth:9000")
    assert client.base_url == "http://custom-auth:9000"


# ──────────────────────────────────────────────
# Consumer integration: auto-fetch email via auth_client
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_consumer_fetches_email_when_send_email_true_and_email_missing():
    """
    When send_email=True and no patient_email in payload,
    the consumer calls auth_client.get_user_email.
    """
    from infrastructure.consumers.appointment_events_consumers import AppointmentConfirmedConsumer

    sink = []
    fake_auth = AsyncMock()
    fake_auth.get_user_email.return_value = "fetched@example.com"

    sf = SessionFactory()
    consumer = AppointmentConfirmedConsumer(
        connection=object(),
        cache=object(),
        session_factory=sf,
        create_notification_use_case_factory=_factory(sink),
        auth_client=fake_auth,
    )

    # Payload without patient_email — auth_client should be called
    await consumer.handle({"patient_id": "u-abc", "auto_confirmed": False})

    assert len(sink) == 1
    fake_auth.get_user_email.assert_called_once_with("u-abc")
    assert sink[0]["recipient_email"] == "fetched@example.com"
    assert sink[0]["send_email"] is True


@pytest.mark.asyncio
async def test_consumer_skips_auth_fetch_when_email_already_in_payload():
    """
    When patient_email is in payload, auth_client.get_user_email is NOT called.
    """
    from infrastructure.consumers.appointment_events_consumers import AppointmentConfirmedConsumer

    sink = []
    fake_auth = AsyncMock()

    sf = SessionFactory()
    consumer = AppointmentConfirmedConsumer(
        connection=object(),
        cache=object(),
        session_factory=sf,
        create_notification_use_case_factory=_factory(sink),
        auth_client=fake_auth,
    )

    await consumer.handle({
        "patient_id": "u-abc",
        "auto_confirmed": True,
        "patient_email": "already@example.com",
    })

    fake_auth.get_user_email.assert_not_called()
    assert sink[0]["recipient_email"] == "already@example.com"


@pytest.mark.asyncio
async def test_consumer_works_without_auth_client():
    """Consumer without auth_client still creates notification (email stays None)."""
    from infrastructure.consumers.appointment_events_consumers import AppointmentDeclinedConsumer

    sink = []
    sf = SessionFactory()
    consumer = AppointmentDeclinedConsumer(
        connection=object(),
        cache=object(),
        session_factory=sf,
        create_notification_use_case_factory=_factory(sink),
        # no auth_client
    )

    await consumer.handle({"patient_id": "p-1"})

    assert len(sink) == 1
    assert sink[0]["recipient_email"] is None


@pytest.mark.asyncio
async def test_consumer_auth_client_fetch_failure_yields_none_email():
    """When auth_client.get_user_email returns None, notification is created with email=None."""
    from infrastructure.consumers.appointment_events_consumers import AppointmentStartedConsumer

    sink = []
    fake_auth = AsyncMock()
    fake_auth.get_user_email.return_value = None  # simulates 404 / network error

    sf = SessionFactory()
    consumer = AppointmentStartedConsumer(
        connection=object(),
        cache=object(),
        session_factory=sf,
        create_notification_use_case_factory=_factory(sink),
        auth_client=fake_auth,
    )

    await consumer.handle({"patient_id": "p-xyz"})

    assert len(sink) == 1
    assert sink[0]["recipient_email"] is None
