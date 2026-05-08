"""Unit tests for UserRegisteredConsumer and UserResendOTPConsumer."""
import asyncio

import pytest
from infrastructure.consumers.user_events_consumers import (
    UserRegisteredConsumer,
    UserResendOTPConsumer,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeEmailSender:
    def __init__(self, fail: bool = False):
        self._fail = fail
        self.sent: list[dict] = []

    async def send_email(self, to: str, subject: str, body: str) -> bool:
        await asyncio.sleep(0)
        if self._fail:
            return False
        self.sent.append({"to": to, "subject": subject, "body": body})
        return True


class FakeCache:
    """Minimal cache stub; idempotency not exercised in unit tests."""

    async def get(self, key: str):
        await asyncio.sleep(0)
        return None

    async def set(self, key: str, value, ex: int | None = None):
        await asyncio.sleep(0)  # no-op stub


def _make_consumer(cls, email_sender):
    """Instantiate a consumer bypassing BaseConsumer.start() to avoid real connection."""
    consumer = object.__new__(cls)
    consumer._connection = None
    consumer._cache = FakeCache()
    consumer._email_sender = email_sender
    return consumer


# ---------------------------------------------------------------------------
# UserRegisteredConsumer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_registered_consumer_sends_otp_email():
    sender = FakeEmailSender()
    consumer = _make_consumer(UserRegisteredConsumer, sender)

    payload = {"user_id": "uid-1", "email": "patient@test.com", "otp": "789012", "role": "patient"}
    await consumer.handle(payload)

    assert len(sender.sent) == 1
    msg = sender.sent[0]
    assert msg["to"] == "patient@test.com"
    assert "789012" in msg["body"]
    assert "HealthAI" in msg["subject"] or "xác thực" in msg["subject"].lower() or "OTP" in msg["subject"]


@pytest.mark.asyncio
async def test_user_registered_consumer_skips_when_no_otp():
    """Staff registrations have no OTP; consumer must skip sending."""
    sender = FakeEmailSender()
    consumer = _make_consumer(UserRegisteredConsumer, sender)

    payload = {"user_id": "uid-2", "email": "doctor@test.com", "role": "doctor"}
    await consumer.handle(payload)

    assert len(sender.sent) == 0


@pytest.mark.asyncio
async def test_user_registered_consumer_skips_when_no_email():
    sender = FakeEmailSender()
    consumer = _make_consumer(UserRegisteredConsumer, sender)

    payload = {"user_id": "uid-3", "otp": "123456"}
    await consumer.handle(payload)

    assert len(sender.sent) == 0


@pytest.mark.asyncio
async def test_user_registered_consumer_otp_appears_in_body():
    sender = FakeEmailSender()
    consumer = _make_consumer(UserRegisteredConsumer, sender)

    otp = "654321"
    await consumer.handle({"user_id": "uid-4", "email": "p@test.com", "otp": otp})

    body = sender.sent[0]["body"]
    assert otp in body


# ---------------------------------------------------------------------------
# UserResendOTPConsumer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resend_otp_consumer_sends_email():
    sender = FakeEmailSender()
    consumer = _make_consumer(UserResendOTPConsumer, sender)

    payload = {"user_id": "uid-5", "email": "p@test.com", "otp": "111222"}
    await consumer.handle(payload)

    assert len(sender.sent) == 1
    assert "111222" in sender.sent[0]["body"]
    assert sender.sent[0]["to"] == "p@test.com"


@pytest.mark.asyncio
async def test_resend_otp_consumer_skips_when_missing_otp():
    sender = FakeEmailSender()
    consumer = _make_consumer(UserResendOTPConsumer, sender)

    await consumer.handle({"user_id": "uid-6", "email": "p@test.com"})
    assert len(sender.sent) == 0


@pytest.mark.asyncio
async def test_resend_otp_consumer_skips_when_missing_email():
    sender = FakeEmailSender()
    consumer = _make_consumer(UserResendOTPConsumer, sender)

    await consumer.handle({"user_id": "uid-7", "otp": "999888"})
    assert len(sender.sent) == 0


@pytest.mark.asyncio
async def test_resend_otp_consumer_same_template_as_registered():
    """Both consumers use the same OTP email body template."""
    sender_reg = FakeEmailSender()
    sender_resend = FakeEmailSender()

    reg_consumer = _make_consumer(UserRegisteredConsumer, sender_reg)
    resend_consumer = _make_consumer(UserResendOTPConsumer, sender_resend)

    otp = "333444"
    payload = {"user_id": "uid-8", "email": "x@test.com", "otp": otp}
    await reg_consumer.handle(payload)
    await resend_consumer.handle(payload)

    # Both should contain the OTP in the body
    assert otp in sender_reg.sent[0]["body"]
    assert otp in sender_resend.sent[0]["body"]
