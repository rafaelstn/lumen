"""avaliar_cnpj (M02): rate limit e crédito esgotado propagam; falha de dado vira score parcial.

Garante que o lote de due diligence/reavaliação possa parar ANTES de gastar a CND quando
o CNPJá retorna 429 por taxa, e que não confunda rate limit transitório com falha de dado.
"""
import pytest

from app.modules.modulo01 import cnpj_lookup as cl
from app.modules.modulo02 import service


@pytest.fixture
def _mock_cnd(monkeypatch):
    chamadas = {"cnd": 0}

    async def _fake_cnd(cnpj, client):
        chamadas["cnd"] += 1
        return {"status": "NEGATIVA"}

    monkeypatch.setattr(service.cnd, "consultar_cnd", _fake_cnd)
    return chamadas


async def test_rate_limit_propaga_sem_rodar_cnd(_mock_cnd, monkeypatch):
    async def _boom(cnpj, client, throttle=None):
        raise cl.RateLimitError("rate", retry_after=5)

    monkeypatch.setattr(service.cnpj_lookup, "consultar_cnpj", _boom)
    with pytest.raises(cl.RateLimitError):
        await service.avaliar_cnpj("37335118000180", client=None)
    assert _mock_cnd["cnd"] == 0  # CND paga não chegou a rodar


async def test_credito_esgotado_propaga_sem_rodar_cnd(_mock_cnd, monkeypatch):
    async def _boom(cnpj, client, throttle=None):
        raise cl.LookupError("Créditos de consulta de CNPJ esgotados.")

    monkeypatch.setattr(service.cnpj_lookup, "consultar_cnpj", _boom)
    with pytest.raises(cl.LookupError):
        await service.avaliar_cnpj("37335118000180", client=None)
    assert _mock_cnd["cnd"] == 0


async def test_falha_pontual_de_dado_vira_score_parcial(_mock_cnd, monkeypatch):
    # LookupError que NÃO é crédito nem rate: segue com dados vazios e ainda roda a CND.
    async def _boom(cnpj, client, throttle=None):
        raise cl.LookupError("Erro 500 na consulta de CNPJ.")

    monkeypatch.setattr(service.cnpj_lookup, "consultar_cnpj", _boom)
    r = await service.avaliar_cnpj("37335118000180", client=None)
    assert r["status_cnd"] == "NEGATIVA"
    assert r["situacao_cadastral"] is None  # sem dados do CNPJá
    assert _mock_cnd["cnd"] == 1
