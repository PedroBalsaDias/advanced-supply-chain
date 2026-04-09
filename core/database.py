"""
Database configuration with SQLAlchemy async support.

Provides database engine, session management, and connection utilities
for PostgreSQL with asyncpg driver.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)

# Base class for all models
Base = declarative_base()

# Global engine instance
_engine: Optional[AsyncEngine] = None
# Global session maker
_session_maker: Optional[async_sessionmaker[AsyncSession]] = None


def get_engine() -> AsyncEngine:
    """
    Get or create async database engine.
    
    Returns:
        AsyncEngine: SQLAlchemy async engine instance
    """
    global _engine
    
    if _engine is None:
        # Use NullPool for testing to avoid connection pool issues
        poolclass = NullPool if settings.environment == "testing" else None
        
        _engine = create_async_engine(
            str(settings.database_url),
            echo=settings.debug,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_pre_ping=True,  # Verify connections before using
            poolclass=poolclass,
            future=True
        )
        logger.info("Database engine created", pool_size=settings.database_pool_size)
    
    return _engine


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    """
    Get or create async session maker.
    
    Returns:
        async_sessionmaker: Session factory for creating async sessions
    """
    global _session_maker
    
    if _session_maker is None:
        _session_maker = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,  # Prevent expired object errors
            autoflush=False,
            autocommit=False
        )
    
    return _session_maker


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for database sessions.
    
    Yields an async session and ensures proper cleanup.
    Handles rollback on exceptions.
    
    Yields:
        AsyncSession: Database session for request handling
        
    Example:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db_session)):
            return await db.execute(select(Item))
    """
    session = get_session_maker()()
    try:
        logger.debug("Database session started")
        yield session
        await session.commit()
        logger.debug("Database session committed")
    except Exception as e:
        await session.rollback()
        logger.error("Database session rolled back due to error", error=str(e))
        raise
    finally:
        await session.close()
        logger.debug("Database session closed")


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager for database sessions.
    
    Useful for background tasks and scripts where FastAPI's
    dependency injection isn't available.
    
    Yields:
        AsyncSession: Database session
        
    Example:
        async with get_db_context() as db:
            result = await db.execute(select(Item))
    """
    session = get_session_maker()()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def init_database() -> None:
    """
    Initialize database schema.
    
    Creates all tables defined in models.
    Should be called during application startup.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        # Import models to ensure they're registered with Base
        from core import models  # noqa: F401
        
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created")


async def close_database() -> None:
    """
    Close database connections.
    
    Should be called during application shutdown.
    """
    global _engine, _session_maker
    
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_maker = None
        logger.info("Database connections closed")
