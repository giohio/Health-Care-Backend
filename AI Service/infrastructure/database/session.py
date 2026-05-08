from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from infrastructure.config import get_settings


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    """Auto-managed created_at and updated_at columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )


def _make_engine_and_session():
    s = get_settings()
    _engine = create_async_engine(s.DATABASE_URL, pool_pre_ping=True)
    _factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return _engine, _factory


engine, AsyncSessionLocal = _make_engine_and_session()


async def get_db():
    """FastAPI dependency: yields a managed AsyncSession."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
