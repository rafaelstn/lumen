"""Fixtures de banco para os testes do módulo de consumo.

Usa SQLite in-memory (aiosqlite) só para os testes: isola do Postgres de produção e
não exige container. Os modelos usam tipos portáveis (String/Integer/Boolean/DateTime),
então o schema cria igual no SQLite.
"""
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models.base import Base
from app.modules.consumo import models as _consumo  # noqa: F401 — registra no metadata


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory():
    """Engine SQLite in-memory COMPARTILHADA entre conexões (StaticPool) + factory de sessões.

    Necessário para testar concorrência: várias sessões precisam enxergar o mesmo banco.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()
