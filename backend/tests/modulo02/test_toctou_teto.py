"""TOCTOU do teto diário (M02): a API paga só roda se a RESERVA do teto for bem-sucedida.

Bug original: o loop checava restante>0 e depois chamava budget.consumir() ignorando o
retorno bool. Sob concorrência, o saldo podia zerar entre o check e o consumir, deixando
estourar o teto e ainda chamar a API paga. A correção usa o retorno de consumir(): se
devolver False, NÃO chama a API, marca teto_atingido e estorna o que já reservou.
"""
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models.base import Base
from app.models import fornecedor as _fornecedor  # noqa: F401 — registra no metadata
from app.modules.consumo import models as _consumo  # noqa: F401
from app.modules.modulo02 import models as _m02  # noqa: F401
from app.modules.modulo02 import repo, service

ESC = "00000000-0000-0000-0000-000000000001"


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    f = async_sessionmaker(engine, expire_on_commit=False)
    async with f() as s:
        yield s
    await engine.dispose()


async def _seed_monitorado(s, cnpj: str) -> None:
    await repo.upsert_monitorado(
        s, ESC,
        {"cnpj": cnpj, "razao_social": "MON", "score": 50, "status_cnd": "NEGATIVA",
         "faixa": "MEDIO", "componentes": {}},
    )


async def test_teto_esgotado_nao_chama_api_paga(session, monkeypatch):
    await _seed_monitorado(session, "11444777000161")

    # Spy: a API paga NÃO pode ser chamada quando a reserva do teto falha.
    chamadas = {"avaliar": 0}

    async def _spy_avaliar(client, cnpj, throttle=None):
        chamadas["avaliar"] += 1
        return {"cnpj": cnpj, "status_cnd": "NEGATIVA", "faixa": "MEDIO", "score": 50}

    monkeypatch.setattr(service, "service_avaliar", _spy_avaliar)
    # Teto já estourado: a reserva (consumir) devolve False de cara.
    monkeypatch.setattr(service.budget, "consumir", lambda servico, n=1: False)

    res = await service.reavaliar_carteira(session, ESC)

    assert res["teto_atingido"] is True
    assert chamadas["avaliar"] == 0  # nenhuma chamada paga sob teto estourado
    assert res["reavaliados"] == 0


async def test_estorna_cnd_quando_cnpj_falha_a_reserva(session, monkeypatch):
    # cnd reserva OK, cnpj estoura: a cnd reservada precisa ser estornada (não inflar o teto)
    # e a API paga não pode rodar nessa iteração.
    await _seed_monitorado(session, "11444777000161")

    devolvidos = []
    reservados = []

    def _consumir(servico, n=1):
        reservados.append(servico)
        return servico == "cnd"  # cnd passa, cnpj falha

    def _devolver(servico, n=1):
        devolvidos.append(servico)

    chamadas = {"avaliar": 0}

    async def _spy_avaliar(client, cnpj, throttle=None):
        chamadas["avaliar"] += 1
        return {"cnpj": cnpj, "status_cnd": "NEGATIVA", "faixa": "MEDIO", "score": 50}

    monkeypatch.setattr(service, "service_avaliar", _spy_avaliar)
    monkeypatch.setattr(service.budget, "consumir", _consumir)
    monkeypatch.setattr(service.budget, "devolver", _devolver)

    res = await service.reavaliar_carteira(session, ESC)

    assert res["teto_atingido"] is True
    assert chamadas["avaliar"] == 0
    assert devolvidos == ["cnd"]  # estornou a cnd que já tinha reservado nessa iteração
