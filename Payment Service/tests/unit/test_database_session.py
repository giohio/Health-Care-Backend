import pytest
from infrastructure.database import session as session_module


@pytest.mark.asyncio
async def test_get_session_yields_value_from_async_session_local(monkeypatch):
    sentinel = object()

    class FakeSessionFactory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return sentinel

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(session_module, "AsyncSessionLocal", FakeSessionFactory())

    agen = session_module.get_session()
    yielded = await anext(agen)
    assert yielded is sentinel
    await agen.aclose()
