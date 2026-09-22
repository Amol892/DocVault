"""Test setup.

The API tests run against a REAL PostgreSQL database (PRD/08-deployment.md), never mocks. To keep
your data safe they use a separate database named `<your database>_test` on the same server, and
refuse to run against anything whose name does not end in `_test`:

  * the database is created on first use, then brought to the latest Alembic revision (so the tests
    also prove the migrations build the schema the models describe), and
  * every table is emptied before each test.
"""

import asyncio
import os
import re
from collections.abc import AsyncIterator

# Settings the app requires. Anything already defined in the environment or a .env file is left
# alone (so the tests find YOUR database); only what is defined nowhere gets a local default.
from dotenv import dotenv_values  # noqa: E402

from app.config import ENV_FILES  # noqa: E402

_DEFAULTS = {
    "DATABASE_URL": "postgresql+asyncpg://docvault:docvault@localhost:5432/docvault",
    "S3_ENDPOINT_URL": "http://localhost:9000",
    "S3_ACCESS_KEY": "test",
    "S3_SECRET_KEY": "test",
}
_defined = {key.upper() for f in ENV_FILES if f.exists() for key in dotenv_values(f)} | set(
    os.environ
)
for _key, _value in _DEFAULTS.items():
    if _key not in _defined:
        os.environ[_key] = _value
# tests sign and verify tokens with a fixed secret, whatever the developer's .env holds
os.environ["JWT_SECRET"] = "test-secret-that-is-at-least-32-characters-long"
# most tests sign users in straight after registering; the verification tests switch it on
os.environ["REQUIRE_EMAIL_VERIFICATION"] = "false"
os.environ["TOKEN_COOLDOWN_SECONDS"] = "0"

import asyncpg  # noqa: E402
import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import URL, make_url  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from alembic import command  # noqa: E402
from app.config import BACKEND_DIR, Settings, get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_session  # noqa: E402
from app.services.mailer import get_mailer  # noqa: E402
from app.storage import get_storage  # noqa: E402
from tests.fake_mailer import FakeMailer  # noqa: E402
from tests.fake_storage import FakeStorage  # noqa: E402


def _test_database_url() -> URL:
    base = make_url(Settings().database_url)
    assert base.database, "DATABASE_URL must name a database"
    name = base.database if base.database.endswith("_test") else f"{base.database}_test"
    assert re.fullmatch(r"[A-Za-z0-9_]+", name), f"unsafe database name: {name}"
    return base.set(database=name)


TEST_URL = _test_database_url()
assert TEST_URL.database and TEST_URL.database.endswith("_test")  # never truncate a real database
# from here on, everything that reads settings (the app, Alembic) sees the test database
os.environ["DATABASE_URL"] = TEST_URL.render_as_string(hide_password=False)
get_settings.cache_clear()

from app.main import app  # noqa: E402  (imported after DATABASE_URL points at the test database)


async def _ensure_database_exists() -> None:
    """Create the _test database if it is missing (connects to the server's `postgres` database)."""
    connection = await asyncpg.connect(
        user=TEST_URL.username,
        password=TEST_URL.password,
        host=TEST_URL.host,
        port=TEST_URL.port,
        database="postgres",
    )
    try:
        exists = await connection.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", TEST_URL.database
        )
        if not exists:
            await connection.execute(f'CREATE DATABASE "{TEST_URL.database}"')
    finally:
        await connection.close()


@pytest.fixture(scope="session")
def test_database() -> None:
    """Create the test database and migrate it to head; fail if the models have drifted from the
    migrations (a model change without a new revision)."""
    asyncio.run(_ensure_database_exists())
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    command.upgrade(config, "head")
    command.check(config)


@pytest.fixture
async def session_factory(test_database: None) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    # a fresh engine per test, created and disposed inside that test's own event loop, so its
    # connections are never shared across loops and can be pooled safely
    engine = create_async_engine(TEST_URL, pool_size=5)
    tables = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def db(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """A session for asserting on, or arranging, database state directly."""
    async with session_factory() as session:
        yield session


@pytest.fixture
def fast_password_hashing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Argon2 with minimal cost for the API tests (each registration and login hashes a password).
    Production parameters are untouched; tests/test_security.py exercises those."""
    from passlib.context import CryptContext

    from app.core import security

    cheap = CryptContext(
        schemes=["argon2"], argon2__time_cost=1, argon2__memory_cost=64, argon2__parallelism=1
    )
    monkeypatch.setattr(security, "_passwords", cheap)
    monkeypatch.setattr(
        security, "_DUMMY_HASH", cheap.hash("password-used-only-to-equalise-timing")
    )


@pytest.fixture
def storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture
def mailer() -> FakeMailer:
    return FakeMailer()


@pytest.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession],
    fast_password_hashing: None,
    storage: FakeStorage,
    mailer: FakeMailer,
) -> AsyncIterator[AsyncClient]:
    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_mailer] = lambda: mailer
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
