"""Async SQLAlchemy engine and session factory for nekospeech.

Uses asyncpg as the underlying driver. All sessions are async and
scoped to request lifetime via the get_db FastAPI dependency.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from nekospeech.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    # Keep low connection usage because this database is shared with Django.
    # Keep low: 2 base + 2 overflow = 4 max per process.
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
