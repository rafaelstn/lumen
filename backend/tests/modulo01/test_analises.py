"""Histórico de análises (Feature 1): persistir, sincronizar, listar, reabrir (re-hidratar), apagar.

Cobre o repo (analises_repo) sobre o SQLite da fixture `session` e os endpoints via TestClient com
factory em memória compartilhada (StaticPool), espelhando test_fornecedor_endpoint.
"""
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app import database
from app.config import settings
from app.main import app
from app.models import analise as _analise  # noqa: F401 — registra no metadata
from app.models import fornecedor as _fornecedor  # noqa: F401
from app.models.base import Base
from app.modules.modulo01 import analises_repo
from app.modules.modulo01.jobs import store

ESCRITORIO = settings.escritorio_default_id


def _forn(cod: str, nome: str, cnpj: str | None, grupo: str) -> dict:
    """Fornecedor com os campos obrigatórios do schema FornecedorResult (reabrir devolve ele)."""
    return {
        "cod_forn": cod,
        "nome_forn": nome,
        "cnpj": cnpj,
        "cnpj_pendente": cnpj is None,
        "cnpj_confirmado": cnpj is not None,
        "grupo": grupo,
        "label": f"Grupo {grupo}",
        "total_compras": 1000.0,
        "total_valor_icms": 180.0,
        "aliquota_max": 18.0,
        "aliquota_efetiva_pct": 18.0,
        "credito_aproveitado": 180.0,
        "credito_perdido": 0.0,
        "n_lancamentos": 3,
    }


def _job(job_id: str, *, cliente="ACME", cnpj_cliente="11222333000181", periodo="2026-01") -> dict:
    return {
        "job_id": job_id,
        "status": "parsed",
        "metadados": {"cliente": cliente, "cnpj_cliente": cnpj_cliente, "periodo": periodo},
        "resumo": {
            "total_fornecedores": 2,
            "grupo_a": 1,
            "grupo_b": 1,
            "grupo_c": 0,
            "caso_especial": 0,
            "total_credito_aproveitado": 180.0,
            "total_compras_sem_credito": 0.0,
            "cnpj_casados": 1,
            "cnpj_pendentes": 1,
        },
        "fornecedores": [
            _forn("1", "FORN A", "12345678000199", "A"),
            _forn("2", "FORN B", None, "B"),
        ],
    }


# --- repo (unidade) -----------------------------------------------------------------


async def test_salvar_cria_e_lista(session):
    await analises_repo.salvar(session, "job-1", _job("job-1"))
    itens = await analises_repo.listar(session, ESCRITORIO)
    assert len(itens) == 1
    assert itens[0].id == "job-1"
    assert itens[0].cliente == "ACME"
    assert itens[0].total_fornecedores == 2


async def test_salvar_idempotente_nao_duplica(session):
    await analises_repo.salvar(session, "job-1", _job("job-1"))
    # Reprocessar a mesma análise (mesmo id) atualiza, não cria uma segunda linha.
    job2 = _job("job-1", cliente="ACME ATUALIZADA")
    await analises_repo.salvar(session, "job-1", job2)
    itens = await analises_repo.listar(session, ESCRITORIO)
    assert len(itens) == 1
    assert itens[0].cliente == "ACME ATUALIZADA"


async def test_sincronizar_atualiza_dados(session):
    await analises_repo.salvar(session, "job-1", _job("job-1"))
    # Simula pós-enriquecimento: o pendente casou e ganhou status de CND/risco.
    job = _job("job-1")
    job["fornecedores"][1]["cnpj"] = "99887766000155"
    job["fornecedores"][1]["status_cnd"] = "NEGATIVA"
    job["fornecedores"][1]["risco_2027"] = "BAIXO"
    await analises_repo.salvar(session, "job-1", job)

    a = await analises_repo.obter(session, "job-1", ESCRITORIO)
    forns = a.dados["fornecedores"]
    assert forns[1]["cnpj"] == "99887766000155"
    assert forns[1]["status_cnd"] == "NEGATIVA"
    assert forns[1]["risco_2027"] == "BAIXO"


async def test_apagar(session):
    await analises_repo.salvar(session, "job-1", _job("job-1"))
    assert await analises_repo.apagar(session, "job-1", ESCRITORIO) is True
    assert await analises_repo.listar(session, ESCRITORIO) == []
    # Apagar de novo não acha nada (idempotente do ponto de vista de erro).
    assert await analises_repo.apagar(session, "job-1", ESCRITORIO) is False


async def test_obter_id_vazio_e_inexistente(session):
    assert await analises_repo.obter(session, "", ESCRITORIO) is None
    assert await analises_repo.obter(session, "nao-existe", ESCRITORIO) is None


# --- endpoints (integração) ---------------------------------------------------------


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


async def test_endpoint_listar_vazio(factory_em_memoria):
    client = TestClient(app)
    resp = client.get("/api/modulo01/analises")
    assert resp.status_code == 200
    assert resp.json() == {"analises": []}


async def test_endpoint_listar_e_reabrir(factory_em_memoria):
    async with factory_em_memoria() as session:
        await analises_repo.salvar(session, "job-x", _job("job-x"))

    client = TestClient(app)
    lista = client.get("/api/modulo01/analises").json()["analises"]
    assert len(lista) == 1
    item = lista[0]
    assert item["id"] == "job-x"
    assert item["cliente"] == "ACME"
    # Lista leve: NÃO carrega o payload de fornecedores.
    assert "fornecedores" not in item

    # Reabrir (job NÃO está no store): recria a partir da Analise, mesmo job_id.
    store.remover("job-x")
    resp = client.get("/api/modulo01/analise/job-x")
    assert resp.status_code == 200
    body = resp.json()
    assert body["job_id"] == "job-x"
    assert body["metadados"]["cliente"] == "ACME"
    assert len(body["fornecedores"]) == 2
    # Contadores de CNPJ recalculados no reabrir.
    assert body["resumo"]["cnpj_casados"] == 1
    assert body["resumo"]["cnpj_pendentes"] == 1


async def test_reabrir_rehidrata_job_no_store(factory_em_memoria):
    async with factory_em_memoria() as session:
        await analises_repo.salvar(session, "job-rehidrata", _job("job-rehidrata"))
    store.remover("job-rehidrata")
    assert store.existe("job-rehidrata") is False

    client = TestClient(app)
    resp = client.get("/api/modulo01/analise/job-rehidrata")
    assert resp.status_code == 200
    # Após reabrir, o job vive no store: o frontend continua enriquecimento/CND com o mesmo id.
    assert store.existe("job-rehidrata") is True
    job = store.obter("job-rehidrata")
    assert job["fornecedores"][0]["cnpj"] == "12345678000199"
    store.remover("job-rehidrata")


async def test_reabrir_usa_job_vivo_se_existir(factory_em_memoria):
    # Histórico tem estado ANTIGO; o store tem estado MAIS NOVO (ex.: enriquecimento concluído).
    async with factory_em_memoria() as session:
        await analises_repo.salvar(session, "job-vivo", _job("job-vivo"))
    vivo = _job("job-vivo")
    vivo["fornecedores"][1]["cnpj"] = "55556666000177"  # pendente já casou no store
    store.criar_com_id("job-vivo", vivo)

    client = TestClient(app)
    body = client.get("/api/modulo01/analise/job-vivo").json()
    # Usou o estado vivo do store (mais à frente), não o histórico antigo.
    assert body["fornecedores"][1]["cnpj"] == "55556666000177"
    assert body["resumo"]["cnpj_casados"] == 2
    store.remover("job-vivo")


async def test_endpoint_reabrir_404(factory_em_memoria):
    client = TestClient(app)
    resp = client.get("/api/modulo01/analise/nao-existe-mesmo")
    assert resp.status_code == 404


async def test_endpoint_apagar(factory_em_memoria):
    async with factory_em_memoria() as session:
        await analises_repo.salvar(session, "job-del", _job("job-del"))
    store.criar_com_id("job-del", _job("job-del"))

    client = TestClient(app)
    resp = client.delete("/api/modulo01/analise/job-del")
    assert resp.status_code == 200
    assert resp.json()["id"] == "job-del"
    # Sumiu do histórico e do store.
    assert client.get("/api/modulo01/analises").json()["analises"] == []
    assert store.existe("job-del") is False
    # Apagar de novo: 404.
    assert client.delete("/api/modulo01/analise/job-del").status_code == 404
