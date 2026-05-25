"""Teste do endpoint GET /api/modulo01/fornecedor/{cnpj} (detalhe sob demanda).

Aponta o async_session_factory do app para um SQLite em memória compartilhado (StaticPool),
semeia um cadastro e valida o shape de resposta + 404. Sócios só aparecem aqui (LGPD).
"""
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app import database
from app.main import app
from app.models import fornecedor as _fornecedor  # noqa: F401 — registra no metadata
from app.models.base import Base
from app.modules.modulo01 import cnpj_lookup, fornecedores_repo
from tests.modulo01.test_fornecedor_cadastro import CNPJ, RECORD


@pytest_asyncio.fixture
async def factory_em_memoria(monkeypatch):
    # Engine único compartilhado (StaticPool): o que o teste semeia, o endpoint enxerga.
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "async_session_factory", factory)
    # O router importa o símbolo por referência ao módulo database; garante o mesmo alvo.
    import app.routers.modulo01 as r
    monkeypatch.setattr(r, "async_session_factory", factory)
    yield factory
    await engine.dispose()


async def test_endpoint_detalhe_devolve_cadastro_e_socios(factory_em_memoria):
    async with factory_em_memoria() as session:
        await fornecedores_repo.salvar_cadastro(session, cnpj_lookup.extrair_cadastro(RECORD), "cnpja")

    client = TestClient(app)
    resp = client.get(f"/api/modulo01/fornecedor/{CNPJ}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["cnpj"] == CNPJ
    assert body["razao_social"] == "ACME INDUSTRIA E COMERCIO LTDA"
    assert body["endereco"]["municipio"] == "SAO PAULO"
    assert body["contato"]["email_principal"] == "contato@acme.com"
    assert body["atividade"]["capital_social_centavos"] == 15000050
    assert len(body["socios"]) == 2
    assert {s["nome"] for s in body["socios"]} == {"JOAO DA SILVA", "MARIA SOUZA"}


async def test_endpoint_detalhe_normaliza_pontuacao(factory_em_memoria):
    async with factory_em_memoria() as session:
        await fornecedores_repo.salvar_cadastro(session, cnpj_lookup.extrair_cadastro(RECORD), "cnpja")
    client = TestClient(app)
    # Pontos e traço (sem a barra, que é separador de path): normaliza para dígitos e casa.
    resp = client.get("/api/modulo01/fornecedor/37.335.118-000180")
    assert resp.status_code == 200
    assert resp.json()["cnpj"] == CNPJ


async def test_endpoint_detalhe_404_inexistente(factory_em_memoria):
    client = TestClient(app)
    resp = client.get("/api/modulo01/fornecedor/00000000000000")
    assert resp.status_code == 404
