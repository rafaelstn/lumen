"""Testes do registro de tentativas SEM sucesso e do skip de já-tentados no enriquecimento.

Motivação (pedido do Rafael): nome que deu nao_encontrado/ambiguo não deve ser repesquisado
no enriquecimento automático (queima crédito à toa). Fica registrado por escritório e é
PULADO no próximo enriquecimento, salvo forcar=true.

Dois níveis de teste:
- Repo puro (registrar_tentativa / nomes_ja_tentados): idempotência e isolamento por tenant.
- Fluxo de background: skip dos já-tentados, forcar re-incluindo, gravação dos não-achados e
  a separação novos x já_tentados (separar_pendentes). Usa um aiosqlite em memória real,
  compartilhado, plugado em enriquecimento.async_session_factory.
"""
import asyncio

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.models import fornecedor as _fornecedor  # noqa: F401 — registra no metadata
from app.models.base import Base
from app.modules.modulo01 import budget, enriquecimento, fornecedores_repo
from app.modules.modulo01 import cnpj_lookup as cl
from app.modules.modulo01.jobs import store

DEFAULT = "00000000-0000-0000-0000-000000000000"


# ---------------------------------------------------------------------------
# Repo puro: idempotência e isolamento por escritório.
# ---------------------------------------------------------------------------
async def test_registrar_tentativa_idempotente_incrementa(session):
    await fornecedores_repo.registrar_tentativa(session, DEFAULT, "Padaria do Zé", "nao_encontrado")
    await fornecedores_repo.registrar_tentativa(session, DEFAULT, "padaria  do  ze", "ambiguo")

    from sqlalchemy import select

    from app.models.fornecedor import EnriquecimentoTentativa

    res = await session.execute(select(EnriquecimentoTentativa))
    linhas = list(res.scalars())
    assert len(linhas) == 1  # mesma chave normalizada: não duplicou
    assert linhas[0].tentativas == 2
    assert linhas[0].resultado == "ambiguo"  # último resultado observado


async def test_nomes_ja_tentados_isolado_por_escritorio(session):
    await fornecedores_repo.registrar_tentativa(session, "esc-A", "ALPHA LTDA", "nao_encontrado")
    await fornecedores_repo.registrar_tentativa(session, "esc-B", "BETA LTDA", "ambiguo")

    a = await fornecedores_repo.nomes_ja_tentados(session, "esc-A")
    b = await fornecedores_repo.nomes_ja_tentados(session, "esc-B")
    assert a == {cl._normalizar("ALPHA LTDA")}
    assert b == {cl._normalizar("BETA LTDA")}
    assert await fornecedores_repo.nomes_ja_tentados(session, "esc-C") == set()


# ---------------------------------------------------------------------------
# Fluxo de background: skip / forcar / gravação dos não-achados / separação.
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def banco(monkeypatch):
    """aiosqlite em memória compartilhado, plugado no enriquecimento (factory real, sem mock)."""
    # StaticPool: uma única conexão compartilhada por toda a engine, senão cada sessão abriria
    # um :memory: novo e vazio (o banco in-memory do aiosqlite é por conexão).
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", future=True, poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(enriquecimento, "async_session_factory", factory)
    yield factory
    await engine.dispose()


@pytest.fixture(autouse=True)
def _isola(monkeypatch):
    """Budget infinito e throttle instantâneo (não toca no asyncio.sleep global)."""
    # Descarta tasks órfãs de um teste anterior cujo loop já fechou (o set é global do módulo);
    # senão o gather de _drenar tentaria aguardar uma task de outro event loop.
    enriquecimento._tasks.clear()
    monkeypatch.setattr(budget, "consumir", lambda servico, n=1: True)
    monkeypatch.setattr(budget, "devolver", lambda servico, n=1: None)
    monkeypatch.setattr(settings, "cnpj_rate_por_min", 100000)
    monkeypatch.setattr(settings, "cnpj_rate_folga", 0.0)
    # Não persiste cadastro/alias/audit (irrelevante aqui e evita ramos sem mock); só as
    # tentativas, que são o objeto do teste, passam pelo repo real via async_session_factory.
    monkeypatch.setattr(fornecedores_repo, "salvar_cadastro", _noop)
    monkeypatch.setattr(fornecedores_repo, "upsert", _noop)
    monkeypatch.setattr(fornecedores_repo, "registrar_alias", _noop)
    monkeypatch.setattr(fornecedores_repo, "associar_escritorio", _noop)
    import app.modules.consumo.repo as consumo_repo

    monkeypatch.setattr(consumo_repo, "registrar_cnpj", _noop_kw)
    # Sincronização do histórico (analises) é ortogonal a este teste; neutraliza para não
    # tocar em outra tabela/sessão dentro da task de background.
    monkeypatch.setattr(enriquecimento, "_sincronizar_historico", _noop)


async def _noop(*a, **k):
    return None


async def _noop_kw(**k):
    return None


def _job(nomes: list[str]) -> str:
    forns = [{"cod_forn": f"F{i}", "nome_forn": n, "cnpj": None} for i, n in enumerate(nomes)]
    return store.criar(
        {"status": "parsed", "fornecedores": forns, "resumo": {}, "metadados": {},
         "escritorio_id": DEFAULT}
    )


def _resultado(mapa: dict[str, str]):
    """Mock de buscar_por_nome: confiança por nome de entrada."""
    async def _fake(nome, uf, client, throttle=None):
        conf = mapa.get(nome, cl.CONF_NAO_ENCONTRADO)
        achou = conf in (cl.CONF_ALTA, cl.CONF_BAIXA)
        return {"cnpj": "37335118000180" if achou else None, "nome_oficial": nome,
                "confianca": conf, "n_candidatos": 1, "cadastro": None}
    return _fake


async def _drenar(job_id: str) -> dict:
    await asyncio.gather(*list(enriquecimento._tasks))
    return store.obter(job_id)["enriquecimento_progresso"]


async def test_nao_encontrado_fica_registrado_e_pula_no_proximo(monkeypatch, banco):
    chamadas = []

    async def _fake(nome, uf, client, throttle=None):
        chamadas.append(nome)
        return {"cnpj": None, "nome_oficial": nome, "confianca": cl.CONF_NAO_ENCONTRADO,
                "n_candidatos": 0, "cadastro": None}

    monkeypatch.setattr(cl, "buscar_por_nome", _fake)

    # 1a passada: pesquisa "FANTASMA", não acha, registra a tentativa.
    job1 = _job(["FANTASMA LTDA"])
    await enriquecimento.iniciar_enriquecimento_job(job1, settings.cnpj_lookup_limite_max)
    await _drenar(job1)
    assert chamadas == ["FANTASMA LTDA"]

    async with banco() as s:
        assert await fornecedores_repo.nomes_ja_tentados(s, DEFAULT) == {cl._normalizar("FANTASMA LTDA")}

    # 2a passada (sem forcar): o mesmo nome é PULADO, não chama a API de novo.
    chamadas.clear()
    job2 = _job(["FANTASMA LTDA"])
    res = await enriquecimento.iniciar_enriquecimento_job(job2, settings.cnpj_lookup_limite_max)
    assert res["total"] == 0  # nada a processar: o único pendente já foi tentado
    await _drenar(job2)
    assert chamadas == []  # não consumiu crédito


async def test_forcar_reinclui_os_ja_tentados(monkeypatch, banco):
    # Pré-popula a tentativa do nome no banco.
    async with banco() as s:
        await fornecedores_repo.registrar_tentativa(s, DEFAULT, "FANTASMA LTDA", "nao_encontrado")

    chamadas = []

    async def _fake(nome, uf, client, throttle=None):
        chamadas.append(nome)
        return {"cnpj": None, "nome_oficial": nome, "confianca": cl.CONF_NAO_ENCONTRADO,
                "n_candidatos": 0, "cadastro": None}

    monkeypatch.setattr(cl, "buscar_por_nome", _fake)

    job = _job(["FANTASMA LTDA"])
    res = await enriquecimento.iniciar_enriquecimento_job(
        job, settings.cnpj_lookup_limite_max, forcar=True
    )
    assert res["total"] == 1  # forçou: re-incluiu o já-tentado
    await _drenar(job)
    assert chamadas == ["FANTASMA LTDA"]  # forçou a re-tentativa
    # Continua sem achar: incrementa a tentativa (não duplica).
    async with banco() as s:
        from sqlalchemy import select

        from app.models.fornecedor import EnriquecimentoTentativa

        linhas = list((await s.execute(select(EnriquecimentoTentativa))).scalars())
        assert len(linhas) == 1
        assert linhas[0].tentativas == 2


async def test_ambiguo_tambem_registra_tentativa(monkeypatch, banco):
    monkeypatch.setattr(cl, "buscar_por_nome", _resultado({"DUPLA LTDA": cl.CONF_AMBIGUO}))
    job = _job(["DUPLA LTDA"])
    await enriquecimento.iniciar_enriquecimento_job(job, settings.cnpj_lookup_limite_max)
    await _drenar(job)
    async with banco() as s:
        assert await fornecedores_repo.nomes_ja_tentados(s, DEFAULT) == {cl._normalizar("DUPLA LTDA")}


async def test_achado_nao_vira_tentativa(monkeypatch, banco):
    monkeypatch.setattr(cl, "buscar_por_nome", _resultado({"BOA LTDA": cl.CONF_ALTA}))
    job = _job(["BOA LTDA"])
    await enriquecimento.iniciar_enriquecimento_job(job, settings.cnpj_lookup_limite_max)
    await _drenar(job)
    async with banco() as s:
        assert await fornecedores_repo.nomes_ja_tentados(s, DEFAULT) == set()


async def test_separar_pendentes_novos_vs_ja_tentados(monkeypatch, banco):
    # "VELHO" já foi tentado; "NOVO 1" e "NOVO 2" nunca.
    async with banco() as s:
        await fornecedores_repo.registrar_tentativa(s, DEFAULT, "VELHO LTDA", "nao_encontrado")

    job = _job(["NOVO 1 LTDA", "VELHO LTDA", "NOVO 2 LTDA"])
    sep = await enriquecimento.separar_pendentes(job)
    assert sep == {"total_pendentes": 3, "novos": 2, "ja_tentados": 1}


async def test_disparo_normal_processa_so_os_novos(monkeypatch, banco):
    async with banco() as s:
        await fornecedores_repo.registrar_tentativa(s, DEFAULT, "VELHO LTDA", "ambiguo")

    chamadas = []

    async def _fake(nome, uf, client, throttle=None):
        chamadas.append(nome)
        return {"cnpj": "37335118000180", "nome_oficial": nome, "confianca": cl.CONF_ALTA,
                "n_candidatos": 1, "cadastro": None}

    monkeypatch.setattr(cl, "buscar_por_nome", _fake)
    job = _job(["NOVO LTDA", "VELHO LTDA"])
    res = await enriquecimento.iniciar_enriquecimento_job(job, settings.cnpj_lookup_limite_max)
    assert res["total"] == 1  # só o novo
    await _drenar(job)
    assert chamadas == ["NOVO LTDA"]  # VELHO foi pulado
