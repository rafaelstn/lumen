"""Fixtures de teste do Módulo 01.

O arquivo real do cliente (idesan.xls) é dado fiscal confidencial e NÃO é
versionado. Coloque-o localmente em backend/tests/fixtures/idesan.xls (ou aponte
a env var IDESAN_FIXTURE). Os testes que dependem dele são pulados se ausente.
"""
import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models import analise as _analise  # noqa: F401 — registra no metadata
from app.models import fornecedor as _fornecedor  # noqa: F401 — registra no metadata

_DEFAULT = os.path.join(os.path.dirname(__file__), "..", "fixtures", "idesan.xls")


@pytest.fixture
def idesan_xls() -> str:
    caminho = os.environ.get("IDESAN_FIXTURE", _DEFAULT)
    if not os.path.exists(caminho):
        pytest.skip(f"Fixture não encontrada: {caminho} (dado confidencial, não versionado)")
    return caminho


@pytest_asyncio.fixture
async def session():
    """SQLite in-memory (aiosqlite) só para os testes de banco. Modelos usam tipos portáveis."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()
