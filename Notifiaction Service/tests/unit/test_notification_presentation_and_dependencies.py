import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from presentation import dependencies
from presentation.dependencies import get_list_notifications_use_case, get_mark_notification_read_use_case
from presentation.routes.notifications import router


class DummyListUC:
    def __init__(self, items):
        self.items = items

    async def execute(self, *_args, **_kwargs):
        await asyncio.sleep(0)
        return self.items


class DummyReadUC:
    def __init__(self, item):
        self.item = item

    async def execute(self, *_args):
        await asyncio.sleep(0)
        return self.item


def _notification(is_read=False):
    return SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        title="Title",
        body="Body",
        event_type="notification.created",
        is_read=is_read,
        created_at=datetime.now(timezone.utc),
        read_at=None,
    )


def test_notification_dependencies_smoke():
    session = object()
    assert dependencies.get_cache_client() is dependencies.get_cache_client()
    assert dependencies.get_db_session(session) is session
    repo = dependencies.get_notification_repo(session)
    assert repo is not None
    assert dependencies.get_ws_manager() is not None
    assert dependencies.get_email_sender() is dependencies.get_email_sender()
    assert dependencies.get_create_notification_use_case(repo, dependencies.get_ws_manager(), dependencies.get_email_sender()) is not None
    assert dependencies.get_list_notifications_use_case(repo) is not None
    assert dependencies.get_mark_notification_read_use_case(repo) is not None


def test_list_notifications_returns_unread_count():
    app = FastAPI()
    app.include_router(router)
    items = [_notification(False), _notification(True)]
    app.dependency_overrides[get_list_notifications_use_case] = lambda: DummyListUC(items)

    client = TestClient(app)
    r = client.get("/me", headers={"X-User-Id": str(uuid4())})

    assert r.status_code == 200
    assert r.json()["unread_count"] == 1


def test_mark_as_read_not_found_returns_404():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_mark_notification_read_use_case] = lambda: DummyReadUC(None)

    client = TestClient(app)
    r = client.put(f"/{uuid4()}/read")

    assert r.status_code == 404
