"""Fixtures de teste do auth/multi-tenant.

Banco em memória (aiosqlite + StaticPool) compartilhado entre o app e os asserts. Cada
módulo de router importa `async_session_factory` por nome, então monkeypatchamos todos.
O rate limiter do slowapi é zerado (limits desabilitados) para os testes não esbarrarem nele.
"""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app import database
from app.config import settings
from app.models.base import Base
from app.models import usuario as _usuario  # noqa: F401 — registra no metadata
from app.models import fornecedor as _fornecedor  # noqa: F401
from app.models import analise as _analise  # noqa: F401
from app.modules.modulo02 import models as _m02  # noqa: F401
from app.modules.consumo import models as _consumo  # noqa: F401

_ROTAS = ("app.routers.auth", "app.routers.admin", "app.routers.modulo01", "app.routers.modulo02")


@pytest_asyncio.fixture
async def factory(monkeypatch):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    f = async_sessionmaker(engine, expire_on_commit=False)

    monkeypatch.setattr(database, "async_session_factory", f)
    import importlib

    for mod in _ROTAS:
        m = importlib.import_module(mod)
        if hasattr(m, "async_session_factory"):
            monkeypatch.setattr(m, "async_session_factory", f)

    # Desliga o rate limiter nos testes (evita 429 ao repetir login/signup).
    from app.ratelimit import limiter

    monkeypatch.setattr(limiter, "enabled", False)
    yield f
    await engine.dispose()


@pytest.fixture
def auth_on(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)


@pytest.fixture
def auth_off(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", False)
