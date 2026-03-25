import asyncio
from uuid import uuid4

import pytest

from Application.use_cases.create_notification import CreateNotificationUseCase


class FakeRepo:
    def __init__(self):
        self.saved = []

    async def save(self, notification):
        await _noop()
        self.saved.append(notification)


class FakeWs:
    def __init__(self):
        self.sent = []

    async def send_to_user(self, user_id, message):
        await _noop()
        self.sent.append((str(user_id), message))


class FakeEmail:
    def __init__(self):
        self.sent = []

    async def send_email(self, to, subject, body):
        await _noop()
        self.sent.append((to, subject, body))


async def _noop():
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_create_notification_saves_and_sends_ws_without_email_by_default():
    repo = FakeRepo()
    ws = FakeWs()
    email = FakeEmail()
    use_case = CreateNotificationUseCase(repo, ws, email)

    user_id = uuid4()
    result = await use_case.execute(
        user_id=user_id,
        title="Payment Created",
        body="Please pay",
        event_type="payment.created",
        recipient_email="patient@example.com",
    )

    assert len(repo.saved) == 1
    assert result.event_type == "payment.created"
    assert len(ws.sent) >= 1
    assert email.sent == []


@pytest.mark.asyncio
async def test_create_notification_sends_email_when_send_email_true():
    repo = FakeRepo()
    ws = FakeWs()
    email = FakeEmail()
    use_case = CreateNotificationUseCase(repo, ws, email)

    await use_case.execute(
        user_id=uuid4(),
        title="Payment Paid",
        body="Success",
        event_type="payment.paid",
        recipient_email="patient@example.com",
        send_email=True,
    )

    assert len(email.sent) == 1
    assert email.sent[0][0] == "patient@example.com"
