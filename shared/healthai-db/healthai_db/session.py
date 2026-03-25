from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def create_session_factory(
    database_url: str, pool_size: int = 10, max_overflow: int = 20, pool_pre_ping: bool = True, echo: bool = False
) -> async_sessionmaker[AsyncSession]:
    """
    Tạo session factory cho 1 service.
    Gọi 1 lần khi khởi động app.

    pool_pre_ping=True: check connection còn sống
    trước khi dùng — tránh stale connections.
    """
    engine = create_async_engine(
        database_url, pool_size=pool_size, max_overflow=max_overflow, pool_pre_ping=pool_pre_ping, echo=echo
    )
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        # expire_on_commit=False quan trọng với async
        # Tránh lazy load sau commit gây lỗi
    )


@asynccontextmanager
async def get_session(session_factory: async_sessionmaker) -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager với auto-rollback khi có exception.

    Usage:
        async with get_session(factory) as session:
            session.add(entity)
            await session.commit()
    """
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
