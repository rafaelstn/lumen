"""Testes do tratamento de rate limit (HTTP 429) do CNPJá.

Cobrem: distinção rate limit x crédito esgotado, retry com backoff no 429 transitório,
e o throttle que espaça as chamadas para não estourar o rate do plano. Cliente HTTP
mockado — nunca chama a API real. O sleep é stubado para o teste ser rápido.
"""
import pytest

from app.config import settings
from app.modules.modulo01 import cnpj_lookup as cl


class _Resp:
    """Resposta HTTP falsa com status, corpo e headers controlados."""

    def __init__(self, status_code: int, payload: dict | None = None, headers: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}
        self.text = text

    def json(self) -> dict:
        return self._payload


class _ClientSequencia:
    """Devolve respostas de uma sequência, uma por GET. Conta as chamadas."""

    def __init__(self, respostas: list[_Resp]):
        self._respostas = list(respostas)
        self.chamadas = 0

    async def get(self, *a, **k):
        self.chamadas += 1
        if not self._respostas:
            raise AssertionError("GET além da sequência esperada")
        return self._respostas.pop(0)


@pytest.fixture(autouse=True)
def _api_key(monkeypatch):
    # _headers() exige a chave; sem isso o lookup falha antes de chegar no 429.
    monkeypatch.setattr(settings, "cnpj_lookup_api_key", "test-key")


@pytest.fixture
def _no_sleep(monkeypatch):
    """Neutraliza o sleep do retry e do throttle para o teste rodar instantâneo."""
    dormidas = []

    async def _fake_sleep(segundos):
        dormidas.append(segundos)

    monkeypatch.setattr(cl.asyncio, "sleep", _fake_sleep)
    return dormidas


def _ok_records(records):
    return _Resp(200, {"records": records})


async def test_429_sem_sinal_de_credito_vira_rate_limit(_no_sleep, monkeypatch):
    # Esgota o retry para o erro propagar; corpo sem sinal de crédito -> RateLimitError.
    monkeypatch.setattr(settings, "cnpj_retry_max", 0)
    client = _ClientSequencia([_Resp(429, text="Too Many Requests")])
    with pytest.raises(cl.RateLimitError):
        await cl.buscar_por_nome("ACME LTDA", None, client)


async def test_429_com_corpo_de_credito_vira_lookup_error(_no_sleep, monkeypatch):
    monkeypatch.setattr(settings, "cnpj_retry_max", 0)
    client = _ClientSequencia([_Resp(429, text="insufficient credits on plan")])
    with pytest.raises(cl.LookupError) as exc:
        await cl.buscar_por_nome("ACME LTDA", None, client)
    assert not isinstance(exc.value, cl.RateLimitError)
    assert "rédit" in str(exc.value)


async def test_429_faz_retry_e_depois_sucesso(_no_sleep, monkeypatch):
    # 1 retry: primeiro 429 transitório, depois 200 com match exato.
    monkeypatch.setattr(settings, "cnpj_retry_max", 2)
    records = [{"taxId": "37335118000180", "head": True, "company": {"name": "ACME LTDA"}}]
    client = _ClientSequencia([_Resp(429, text="rate"), _ok_records(records)])
    r = await cl.buscar_por_nome("ACME LTDA", None, client)
    assert r["confianca"] == cl.CONF_ALTA
    assert client.chamadas == 2
    assert len(_no_sleep) == 1  # dormiu uma vez no retry


async def test_429_retry_respeita_retry_after(_no_sleep, monkeypatch):
    monkeypatch.setattr(settings, "cnpj_retry_max", 1)
    monkeypatch.setattr(settings, "cnpj_retry_backoff_teto_s", 30.0)
    records = [{"taxId": "37335118000180", "head": True, "company": {"name": "ACME LTDA"}}]
    client = _ClientSequencia([_Resp(429, headers={"Retry-After": "5"}, text="rate"), _ok_records(records)])
    await cl.buscar_por_nome("ACME LTDA", None, client)
    assert _no_sleep == [5.0]  # respeitou o Retry-After da origem


async def test_429_retry_respeita_teto_de_espera(_no_sleep, monkeypatch):
    # Retry-After absurdo é limitado pelo teto para não estourar o request HTTP.
    monkeypatch.setattr(settings, "cnpj_retry_max", 1)
    monkeypatch.setattr(settings, "cnpj_retry_backoff_teto_s", 8.0)
    records = [{"taxId": "37335118000180", "head": True, "company": {"name": "ACME LTDA"}}]
    client = _ClientSequencia([_Resp(429, headers={"Retry-After": "600"}, text="rate"), _ok_records(records)])
    await cl.buscar_por_nome("ACME LTDA", None, client)
    assert _no_sleep == [8.0]


async def test_429_persistente_esgota_retry_e_propaga_rate_limit(_no_sleep, monkeypatch):
    monkeypatch.setattr(settings, "cnpj_retry_max", 2)
    client = _ClientSequencia([_Resp(429, text="rate"), _Resp(429, text="rate"), _Resp(429, text="rate")])
    with pytest.raises(cl.RateLimitError):
        await cl.buscar_por_nome("ACME LTDA", None, client)
    assert client.chamadas == 3  # 1 original + 2 retries


async def test_consultar_cnpj_429_tambem_distingue(_no_sleep, monkeypatch):
    # Mesmo tratamento no consultar_cnpj (usado pelo lote do M02).
    monkeypatch.setattr(settings, "cnpj_retry_max", 0)
    client = _ClientSequencia([_Resp(429, text="too many requests")])
    with pytest.raises(cl.RateLimitError):
        await cl.consultar_cnpj("37335118000180", client)


async def test_consultar_cnpj_404_nao_e_erro(_no_sleep):
    client = _ClientSequencia([_Resp(404)])
    r = await cl.consultar_cnpj("37335118000180", client)
    assert r == {"cnpj": "37335118000180", "encontrado": False}


async def test_throttle_espaca_chamadas(monkeypatch):
    # O throttle deve dormir ~intervalo entre chamadas para não passar do rate/min.
    dormidas = []

    async def _fake_sleep(segundos):
        dormidas.append(segundos)

    monkeypatch.setattr(cl.asyncio, "sleep", _fake_sleep)
    monkeypatch.setattr(settings, "cnpj_rate_por_min", 10)
    monkeypatch.setattr(settings, "cnpj_rate_folga", 0.0)

    throttle = cl.novo_throttle()
    records = [{"taxId": "37335118000180", "head": True, "company": {"name": "ACME"}}]
    client = _ClientSequencia([_ok_records(records), _ok_records(records), _ok_records(records)])
    for _ in range(3):
        await cl.buscar_por_nome("ACME", None, client, throttle=throttle)

    # Primeira chamada não espera; as duas seguintes dormem ~6s (60/10) cada.
    assert len(dormidas) == 2
    assert all(abs(d - 6.0) < 0.5 for d in dormidas)


def test_intervalo_do_throttle_inclui_folga():
    t = cl._Throttle(10, folga=0.2)
    assert abs(t._intervalo - 7.2) < 1e-6  # (60/10) * 1.2
