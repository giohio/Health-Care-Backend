import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from Application.use_cases.create_notification import CreateNotificationUseCase
from Application.use_cases.list_notifications import ListNotificationsUseCase
from pydantic import ValidationError


class FakeRepo:
    def __init__(self, notifications=None):
        self.saved = []
        self.notifications = notifications or []

    async def save(self, notification):
        await asyncio.sleep(0)
        self.saved.append(notification)

    async def list_by_user(self, user_id, limit=50, offset=0):
        await asyncio.sleep(0)
        return self.notifications


class FakeWs:
    def __init__(self):
        self.sent = []

    async def send_to_user(self, user_id, message):
        await asyncio.sleep(0)
        self.sent.append((str(user_id), message))


class FakeEmail:
    def __init__(self):
        self.sent = []

    async def send_email(self, to, subject, body):
        await asyncio.sleep(0)
        self.sent.append((to, subject, body))


@pytest.mark.asyncio
async def test_create_notification_sends_twice_when_uuid_needs_canonicalization():
    repo = FakeRepo()
    ws = FakeWs()
    use_case = CreateNotificationUseCase(repo=repo, ws_manager=ws, email_sender=None)

    raw_user_id = "{" + str(uuid4()) + "}"
    await use_case.execute(
        user_id=raw_user_id,
        title="Title",
        body="Body",
        event_type="event.test",
    )

    assert len(ws.sent) == 2


@pytest.mark.asyncio
async def test_create_notification_invalid_uuid_raises_validation_error():
    repo = FakeRepo()
    ws = FakeWs()
    use_case = CreateNotificationUseCase(repo=repo, ws_manager=ws, email_sender=FakeEmail())

    with pytest.raises(ValidationError):
        await use_case.execute(
            user_id="not-a-uuid",
            title="Title",
            body="Body",
            event_type="event.test",
            recipient_email="a@b.com",
            send_email=True,
        )

    assert ws.sent == []


@pytest.mark.asyncio
async def test_list_notifications_returns_empty_list_when_repo_empty():
    use_case = ListNotificationsUseCase(repo=FakeRepo(notifications=[]))

    result = await use_case.execute(user_id=uuid4())

    assert result == []


@pytest.mark.asyncio
async def test_list_notifications_maps_multiple_notification_types():
    user_id = uuid4()
    notifications = [
        {
            "id": uuid4(),
            "user_id": user_id,
            "title": "Payment",
            "body": "Paid",
            "event_type": "payment.paid",
            "is_read": False,
            "created_at": datetime.now(timezone.utc),
            "read_at": None,
        },
        {
            "id": uuid4(),
            "user_id": user_id,
            "title": "Appointment",
            "body": "Scheduled",
            "event_type": "appointment.created",
            "is_read": False,
            "created_at": datetime.now(timezone.utc),
            "read_at": None,
        },
    ]

    use_case = ListNotificationsUseCase(repo=FakeRepo(notifications=notifications))
    result = await use_case.execute(user_id=user_id)

    assert len(result) == 2
    assert {item.type for item in result} == {"payment", "appointment"}
