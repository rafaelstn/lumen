"""Testes da consulta CND (Fase 3) com cliente HTTP mockado, sem chamar a Infosimples."""
import httpx
import pytest

from app.config import settings
from app.modules.modulo01 import cnd


@pytest.fixture(autouse=True)
def _retry_sem_espera(monkeypatch):
    """Zera o backoff para o retry não dormir nos testes (mantém o teto de tentativas)."""
    monkeypatch.setattr(settings, "cnd_retry_backoff_s", 0.0)
    monkeypatch.setattr(settings, "cnd_retry_backoff_teto_s", 0.0)


def test_tem_debitos():
    assert cnd._tem_debitos({"debitos_rfb": [{"x": 1}]}) is True
    assert cnd._tem_debitos({"debitos_pgfn": ["a"]}) is True
    assert cnd._tem_debitos({}) is False
    assert cnd._tem_debitos({"debitos_rfb": [], "debitos_pgfn": None}) is False


def test_mapear_status():
    assert cnd._mapear_status({"conseguiu_emitir_certidao_negativa": True}) == cnd.NEGATIVA
    assert (
        cnd._mapear_status({"conseguiu_emitir_certidao_negativa": True, "debitos_rfb": [{}]})
        == cnd.POSITIVA_EFEITO_NEGATIVA
    )
    assert cnd._mapear_status({"conseguiu_emitir_certidao_negativa": False}) == cnd.POSITIVA
    # Campo ausente/indeterminado não pode virar "regular".
    assert cnd._mapear_status({}) == cnd.FALHA


def test_mascara_cnpj_nao_expoe_numero():
    m = cnd._mascara_cnpj("51260859000170")
    assert "51260859" not in m and m.startswith("51.")


class _FakeResp:
    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


class _FakeClient:
    """Devolve um payload fixo e conta quantas vezes foi chamado (para verificar retry)."""

    def __init__(self, payload):
        self._p = payload
        self.chamadas = 0

    async def post(self, *a, **k):
        self.chamadas += 1
        return _FakeResp(self._p)


class _SequenciaClient:
    """Devolve um payload diferente a cada chamada (lista de payloads em ordem)."""

    def __init__(self, payloads):
        self._payloads = list(payloads)
        self.chamadas = 0

    async def post(self, *a, **k):
        idx = min(self.chamadas, len(self._payloads) - 1)
        self.chamadas += 1
        return _FakeResp(self._payloads[idx])


# Retorno real da Infosimples (data[0]) capturado numa consulta verdadeira.
_DATA_REAL_NEGATIVA = {
    "code": 200,
    "data": [
        {
            "certidao": "Certidão Negativa de Débitos relativos a Tributos Federais...",
            "certidao_codigo": "078A.05F6.FFC6.C668",
            "conseguiu_emitir_certidao_negativa": True,
            "consulta_datahora": "25/05/2026 23:18:17",
            "debitos_rfb": False,
            "debitos_pgfn": False,
            "emissao_data": "25/05/2026",
            "validade_data": "21/11/2026",
            "situacao": "Negativa",
            "descricao": None,
            "site_receipt": None,
        }
    ],
}


async def test_consultar_cnd_negativa():
    client = _FakeClient({"code": 200, "data": [{"conseguiu_emitir_certidao_negativa": True}]})
    r = await cnd.consultar_cnd("51260859000170", client)
    assert r["status"] == cnd.NEGATIVA


async def test_consultar_cnd_positiva():
    client = _FakeClient({"code": 200, "data": [{"conseguiu_emitir_certidao_negativa": False}]})
    r = await cnd.consultar_cnd("51260859000170", client)
    assert r["status"] == cnd.POSITIVA


async def test_consultar_cnd_captura_todos_os_campos():
    client = _FakeClient(_DATA_REAL_NEGATIVA)
    r = await cnd.consultar_cnd("51260859000170", client)
    assert r["status"] == cnd.NEGATIVA
    assert r["certidao_codigo"] == "078A.05F6.FFC6.C668"
    assert r["cnd_tipo"].startswith("Certidão Negativa")
    assert r["cnd_emissao_data"] == "25/05/2026"
    assert r["validade_data"] == "21/11/2026"
    assert r["cnd_consulta_datahora"] == "25/05/2026 23:18:17"
    assert r["cnd_debitos_rfb"] is False
    assert r["cnd_debitos_pgfn"] is False
    assert r["cnd_comprovante_url"] is None
    # Campo interno do retry não vaza no retorno.
    assert "_transitoria" not in r


async def test_consultar_cnd_code_erro_captura_motivo():
    client = _FakeClient({"code": 605, "code_message": "CNPJ não encontrado na base.", "data": []})
    r = await cnd.consultar_cnd("51260859000170", client)
    assert r["status"] == cnd.FALHA
    assert r["cnd_falha_motivo"] == "CNPJ não encontrado na base."
    # Code definitivo (605): uma única chamada, sem retry.
    assert client.chamadas == 1


async def test_consultar_cnd_excecao_de_rede_vira_falha_com_motivo():
    class _Boom:
        def __init__(self):
            self.chamadas = 0

        async def post(self, *a, **k):
            self.chamadas += 1
            raise httpx.ConnectError("boom")

    boom = _Boom()
    r = await cnd.consultar_cnd("51260859000170", boom)
    assert r["status"] == cnd.FALHA
    assert r["cnd_falha_motivo"]
    # Erro de rede é transitório: re-tenta até o teto (1 + cnd_retry_max).
    assert boom.chamadas == 1 + settings.cnd_retry_max


async def test_retry_transitoria_vira_sucesso():
    # Primeira chamada 429 (transitória), segunda 200 negativa.
    client = _SequenciaClient([
        {"code": 429, "code_message": "Limite de requisições.", "data": []},
        {"code": 200, "data": [{"conseguiu_emitir_certidao_negativa": True}]},
    ])
    r = await cnd.consultar_cnd("51260859000170", client)
    assert r["status"] == cnd.NEGATIVA
    assert client.chamadas == 2


async def test_retry_definitiva_nao_retenta():
    # Code 605 (definitivo): não re-tenta mesmo com retry habilitado.
    client = _FakeClient({"code": 605, "code_message": "CNPJ inválido.", "data": []})
    r = await cnd.consultar_cnd("51260859000170", client)
    assert r["status"] == cnd.FALHA
    assert client.chamadas == 1


async def test_retry_transitoria_nao_estoura_o_teto():
    # 5xx em todas as chamadas: re-tenta, mas para no teto e devolve FALHA.
    client = _FakeClient({"code": 500, "code_message": "Instabilidade na fonte.", "data": []})
    r = await cnd.consultar_cnd("51260859000170", client)
    assert r["status"] == cnd.FALHA
    assert client.chamadas == 1 + settings.cnd_retry_max


async def test_code_615_marca_origem_fora():
    # 615 = site/aplicativo de origem (Receita/PGFN) indisponível: é a FONTE fora do ar.
    client = _FakeClient({
        "code": 615,
        "code_message": "O site ou aplicativo de origem parece estar indisponível.",
        "data": [],
    })
    r = await cnd.consultar_cnd("51260859000170", client)
    assert r["status"] == cnd.FALHA
    assert r["origem_fora"] is True
    # Campo interno do retry não vaza.
    assert "_origem_fora" not in r


async def test_falha_comum_nao_marca_origem_fora():
    # 605 (CNPJ não encontrado) é defeito de negócio, não fonte fora do ar.
    client = _FakeClient({"code": 605, "code_message": "CNPJ não encontrado.", "data": []})
    r = await cnd.consultar_cnd("51260859000170", client)
    assert r["status"] == cnd.FALHA
    assert r["origem_fora"] is False


async def test_sucesso_nao_marca_origem_fora():
    client = _FakeClient({"code": 200, "data": [{"conseguiu_emitir_certidao_negativa": True}]})
    r = await cnd.consultar_cnd("51260859000170", client)
    assert r["status"] == cnd.NEGATIVA
    assert r["origem_fora"] is False
