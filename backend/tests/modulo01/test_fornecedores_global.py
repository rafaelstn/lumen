"""Listagem global de fornecedores (Feature 2): paginação, total, filtro q, SEM sócios (LGPD).

Cobre o repo (listar_paginado) sobre a fixture `session` e o endpoint GET /api/modulo01/fornecedores
via TestClient com factory em memória compartilhada (StaticPool).
"""
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app import database
from app.main import app
from app.models import fornecedor as _fornecedor  # noqa: F401 — registra no metadata
from app.models.base import Base
from app.modules.modulo01 import fornecedores_repo


async def _semear(session, n: int) -> None:
    for i in range(n):
        cnpj = f"{i:014d}"
        await fornecedores_repo.salvar_cadastro(
            session,
            {
                "cnpj": cnpj,
                "razao_social": f"FORNECEDOR {i:03d} LTDA",
                "municipio": "SAO PAULO",
                "uf": "SP",
                "cnae_principal_descricao": "Comercio",
                "situacao_cadastral": "ATIVA",
                "socios": [{"nome": f"SOCIO {i}", "qualificacao": "Administrador"}],
            },
            "cnpja",
        )


# --- repo ---------------------------------------------------------------------------


async def test_listar_paginado_total_e_pagina(session):
    await _semear(session, 5)
    pagina, total = await fornecedores_repo.listar_paginado(session, offset=0, limite=2)
    assert total == 5
    assert len(pagina) == 2
    pagina2, total2 = await fornecedores_repo.listar_paginado(session, offset=4, limite=2)
    assert total2 == 5
    assert len(pagina2) == 1


async def test_listar_paginado_filtro_q_por_nome(session):
    await _semear(session, 3)
    pagina, total = await fornecedores_repo.listar_paginado(session, offset=0, limite=50, q="002")
    assert total == 1
    assert pagina[0].razao_social == "FORNECEDOR 002 LTDA"


async def test_listar_paginado_filtro_q_por_cnpj(session):
    await _semear(session, 3)
    # CNPJ do índice 1 = "00000000000001".
    pagina, total = await fornecedores_repo.listar_paginado(session, offset=0, limite=50, q="00000000000001")
    assert total == 1
    assert pagina[0].cnpj == "00000000000001"


# --- endpoint ----------------------------------------------------------------------


@pytest_asyncio.fixture
async def factory_em_memoria(monkeypatch):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "async_session_factory", factory)
    import app.routers.modulo01 as r
    monkeypatch.setattr(r, "async_session_factory", factory)
    yield factory
    await engine.dispose()


async def test_endpoint_lista_paginada_sem_socios(factory_em_memoria):
    async with factory_em_memoria() as session:
        await _semear(session, 3)

    client = TestClient(app)
    resp = client.get("/api/modulo01/fornecedores?offset=0&limit=2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert len(body["resultados"]) == 2
    item = body["resultados"][0]
    # Cadastro presente, mas NUNCA sócios (LGPD).
    assert "socios" not in item
    assert item["municipio"] == "SAO PAULO"
    assert item["situacao_cadastral"] == "ATIVA"


async def test_endpoint_filtro_q(factory_em_memoria):
    async with factory_em_memoria() as session:
        await _semear(session, 3)
    client = TestClient(app)
    body = client.get("/api/modulo01/fornecedores?q=001").json()
    assert body["total"] == 1
    assert body["resultados"][0]["razao_social"] == "FORNECEDOR 001 LTDA"


async def test_endpoint_limit_clamp_anti_abuso(factory_em_memoria):
    client = TestClient(app)
    # limit acima do teto (100) é saneado para 100.
    body = client.get("/api/modulo01/fornecedores?limit=9999").json()
    assert body["limit"] == 100
