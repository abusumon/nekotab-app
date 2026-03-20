"""Async SQLAlchemy engine and session factory for nekocongress.

Uses asyncpg as the underlying driver. All sessions are async and
scoped to request lifetime via the get_db FastAPI dependency.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from nekocongress.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_size=2,
    max_overflow=2,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async DB session."""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
