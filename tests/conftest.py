"""
Configuração de testes — SQLite em arquivo temporário para isolamento.
"""
import os
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.main import app

_TEST_DB_FILE = "./test_podium.db"
_TEST_DB_URL = f"sqlite+aiosqlite:///{_TEST_DB_FILE}"

_engine = create_async_engine(_TEST_DB_URL, connect_args={"check_same_thread": False})
_TestSessionLocal = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)


async def _override_get_db():
    async with _TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = _override_get_db


@pytest_asyncio.fixture(autouse=True)
async def reset_db():
    """Recria todas as tabelas antes de cada teste, garantindo isolamento."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Limpeza pós-teste opcional (o drop_all no próximo teste já cuida)


@pytest_asyncio.fixture
async def client(reset_db):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


def pytest_sessionfinish(session, exitstatus):
    """Remove o arquivo de banco de dados após os testes."""
    try:
        if os.path.exists(_TEST_DB_FILE):
            os.remove(_TEST_DB_FILE)
    except OSError:
        pass  # Windows pode manter o lock por um momento
