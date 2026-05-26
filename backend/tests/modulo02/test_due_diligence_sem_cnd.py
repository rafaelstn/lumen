"""Due diligence com opção `incluir_cnd` (avaliar só o cadastro, sem CND).

Sem CND (incluir_cnd=False): não chama a Infosimples (zero consulta paga de CND), não exige
o token, só reserva/consome o crédito de cadastro (cnpj), score sai parcial (sem o componente
de regularidade) e status_cnd volta None. Com CND (default): comportamento atual preservado.

Testa pelo endpoint HTTP para cobrir token + budget + contrato de resposta de uma vez. O audit
trail (banco) é resiliente a falha, então roda sem Postgres real.
"""
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.modules.modulo01 import budget
from app.modules.modulo02 import service
from app.ratelimit import limiter

# CNPJ válido (dígitos verificadores corretos) para passar pelo normalizador.
CNPJ = "11444777000161"


@pytest.fixture(autouse=True)
def _sem_rate_limit():
    # Vários POSTs do mesmo IP de teste estourariam o 4/minute. O foco aqui é o contrato,
    # não o rate limit (coberto à parte). Restaura ao fim para não vazar estado entre testes.
    anterior = limiter.enabled
    limiter.enabled = False
    yield
    limiter.enabled = anterior


@pytest.fixture
def ambiente(monkeypatch):
    """Mocka o CNPJá (cadastro fixo) e espiona a CND e o budget. Garante token presente
    para provar que, sem CND, ele simplesmente não é exigido (e não é o que destrava)."""
    monkeypatch.setattr(settings, "infosimples_token", "tok-de-teste")

    chamadas = {"cnd": 0}
    reservas: list[str] = []

    async def _fake_cnpj(cnpj, client, throttle=None):
        # Lucro Real, ativa, madura: dá score alto no cadastro (sem depender da CND).
        return {
            "nome_oficial": "ACME LTDA",
            "situacao_cadastral": "ATIVA",
            "simples_optante": False,
            "fundacao": "2010-01-01",
            "cadastro": None,
        }

    async def _spy_cnd(cnpj, client):
        chamadas["cnd"] += 1
        return {"status": "NEGATIVA", "origem_fora": False}

    def _spy_consumir(servico, n=1):
        reservas.append(servico)
        return True

    monkeypatch.setattr(service.cnpj_lookup, "consultar_cnpj", _fake_cnpj)
    monkeypatch.setattr(service.cnd, "consultar_cnd", _spy_cnd)
    monkeypatch.setattr(budget, "consumir", _spy_consumir)
    monkeypatch.setattr(budget, "devolver", lambda servico, n=1: None)
    return {"chamadas": chamadas, "reservas": reservas}


def test_sem_cnd_nao_chama_infosimples_e_so_consome_cadastro(ambiente):
    client = TestClient(app)
    resp = client.post(
        "/api/modulo02/due-diligence", json={"cnpjs": [CNPJ], "incluir_cnd": False}
    )
    assert resp.status_code == 200
    body = resp.json()

    # Zero chamada à Infosimples.
    assert ambiente["chamadas"]["cnd"] == 0
    # Só reservou crédito de cadastro (cnpj), nunca de CND.
    assert "cnd" not in ambiente["reservas"]
    assert "cnpj" in ambiente["reservas"]

    assert body["incluiu_cnd"] is False
    assert body["avaliados"] == 1
    r = body["resultados"][0]
    # status_cnd None = "não consultado".
    assert r["status_cnd"] is None
    # Score parcial: o componente de regularidade (cnd) não entra.
    assert "cnd" not in r["componentes"]
    # Cadastro pleno ainda pontua (regime + situação + maturidade = 30 + 25 + 10).
    assert r["score"] == 65


def test_sem_cnd_nao_exige_token(ambiente, monkeypatch):
    # Sem token configurado, o modo sem CND ainda funciona (não depende da Infosimples).
    monkeypatch.setattr(settings, "infosimples_token", "")
    client = TestClient(app)
    resp = client.post(
        "/api/modulo02/due-diligence", json={"cnpjs": [CNPJ], "incluir_cnd": False}
    )
    assert resp.status_code == 200
    assert resp.json()["avaliados"] == 1
    assert ambiente["chamadas"]["cnd"] == 0


def test_com_cnd_default_consulta_infosimples(ambiente):
    client = TestClient(app)
    # Sem o campo: default True (comportamento atual).
    resp = client.post("/api/modulo02/due-diligence", json={"cnpjs": [CNPJ]})
    assert resp.status_code == 200
    body = resp.json()

    assert body["incluiu_cnd"] is True
    assert ambiente["chamadas"]["cnd"] == 1  # CND foi consultada
    # Reservou os dois créditos (cnd + cnpj).
    assert "cnd" in ambiente["reservas"]
    assert "cnpj" in ambiente["reservas"]

    r = body["resultados"][0]
    assert r["status_cnd"] == "NEGATIVA"
    assert "cnd" in r["componentes"]
    # Cadastro (65) + CND NEGATIVA (35) = 100.
    assert r["score"] == 100


def test_com_cnd_sem_token_continua_bloqueado(ambiente, monkeypatch):
    # Regressão: com CND e sem token, segue 400 (comportamento atual preservado).
    monkeypatch.setattr(settings, "infosimples_token", "")
    client = TestClient(app)
    resp = client.post("/api/modulo02/due-diligence", json={"cnpjs": [CNPJ], "incluir_cnd": True})
    assert resp.status_code == 400


def test_origem_indisponivel_propaga_para_o_retorno(ambiente, monkeypatch):
    # CND falha por origem fora do ar: o due-diligence sinaliza origem_indisponivel > 0.
    async def _cnd_origem_fora(cnpj, client):
        return {"status": "FALHA", "origem_fora": True}

    monkeypatch.setattr(service.cnd, "consultar_cnd", _cnd_origem_fora)
    client = TestClient(app)
    resp = client.post("/api/modulo02/due-diligence", json={"cnpjs": [CNPJ], "incluir_cnd": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body["origem_indisponivel"] == 1
    assert body["resultados"][0]["origem_fora"] is True
