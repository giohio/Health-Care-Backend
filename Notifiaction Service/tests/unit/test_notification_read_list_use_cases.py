import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from Application.use_cases.list_notifications import ListNotificationsUseCase
from Application.use_cases.mark_notification_read import MarkNotificationReadUseCase


class FakeRepo:
    def __init__(self, notifications=None, mark_result=None):
        self.notifications = notifications or []
        self.mark_result = mark_result
        self.list_calls = []
        self.mark_calls = []

    async def list_by_user(self, user_id, limit=50, offset=0):
        await asyncio.sleep(0)
        self.list_calls.append((user_id, limit, offset))
        return self.notifications

    async def mark_read(self, notification_id):
        await asyncio.sleep(0)
        self.mark_calls.append(notification_id)
        return self.mark_result


@pytest.mark.asyncio
async def test_list_notifications_returns_dto_list():
    user_id = uuid4()
    sample = {
        "id": uuid4(),
        "user_id": user_id,
        "title": "Payment paid",
        "body": "Done",
        "event_type": "payment.paid",
        "is_read": False,
        "created_at": datetime.now(timezone.utc),
        "read_at": None,
    }
    repo = FakeRepo(notifications=[sample])
    use_case = ListNotificationsUseCase(repo=repo)

    result = await use_case.execute(user_id=user_id, limit=10, offset=5)

    assert len(result) == 1
    assert result[0].event_type == "payment.paid"
    assert result[0].type == "payment"
    assert repo.list_calls[0][1:] == (10, 5)


@pytest.mark.asyncio
async def test_mark_notification_read_returns_none_when_missing():
    repo = FakeRepo(mark_result=None)
    use_case = MarkNotificationReadUseCase(repo=repo)

    result = await use_case.execute(notification_id=uuid4())

    assert result is None
    assert len(repo.mark_calls) == 1


@pytest.mark.asyncio
async def test_mark_notification_read_returns_dto_when_found():
    notification_id = uuid4()
    sample = {
        "id": notification_id,
        "user_id": uuid4(),
        "title": "Payment refunded",
        "body": "Refund done",
        "event_type": "payment.refunded",
        "is_read": True,
        "created_at": datetime.now(timezone.utc),
        "read_at": datetime.now(timezone.utc),
    }
    repo = FakeRepo(mark_result=sample)
    use_case = MarkNotificationReadUseCase(repo=repo)

    result = await use_case.execute(notification_id=notification_id)

    assert result is not None
    assert result.is_read is True
    assert result.type == "payment"
