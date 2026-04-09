"""
Pytest configuration and fixtures.
"""

import asyncio
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from api.main import app
from core.config import Settings, get_settings
from core.database import Base, get_db_session
from core.models import User
from core.security import get_password_hash

# Test database URL
TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/supplychain_test"

# Create test engine
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    poolclass=NullPool,
    future=True
)

# Test session maker
test_session_maker = sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False
)


# Override settings for testing
def get_test_settings() -> Settings:
    """Get test-specific settings."""
    return Settings(
        database_url=TEST_DATABASE_URL,
        debug=True,
        environment="testing",
        secret_key="test-secret-key",
        redis_url="redis://localhost:6379/15",  # Use separate DB for tests
    )


# Fixture for event loop
@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# Fixture for database setup
@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database() -> AsyncGenerator[None, None]:
    """Create test database tables."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield
    
    # Cleanup
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# Fixture for database session
@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create test database session."""
    session = test_session_maker()
    
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()


# Fixture for FastAPI test client
@pytest.fixture
def client(db_session: AsyncSession) -> Generator[TestClient, None, None]:
    """Create FastAPI test client with overridden dependencies."""
    
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_settings] = get_test_settings
    app.dependency_overrides[get_db_session] = override_get_db
    
    with TestClient(app) as test_client:
        yield test_client
    
    app.dependency_overrides.clear()


# Fixture for async HTTP client
@pytest_asyncio.fixture
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP client for testing."""
    
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_settings] = get_test_settings
    app.dependency_overrides[get_db_session] = override_get_db
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
    
    app.dependency_overrides.clear()


# Fixture for test user
@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create test user."""
    user = User(
        email="test@example.com",
        hashed_password=get_password_hash("testpassword"),
        full_name="Test User",
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


# Fixture for authentication headers
@pytest.fixture
def auth_headers(test_user: User) -> dict:
    """Get authentication headers for test user."""
    from api.routers.auth import create_access_token
    
    access_token = create_access_token(str(test_user.id))
    return {"Authorization": f"Bearer {access_token}"}
