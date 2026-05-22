"""Testes da consulta CND (Fase 3) com cliente HTTP mockado — não chama a Infosimples."""
import httpx
import pytest

from app.modules.modulo01 import cnd


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
    def __init__(self, payload):
        self._p = payload

    async def post(self, *a, **k):
        return _FakeResp(self._p)


async def test_consultar_cnd_negativa():
    client = _FakeClient({"code": 200, "data": [{"conseguiu_emitir_certidao_negativa": True}]})
    r = await cnd.consultar_cnd("51260859000170", client)
    assert r["status"] == cnd.NEGATIVA


async def test_consultar_cnd_positiva():
    client = _FakeClient({"code": 200, "data": [{"conseguiu_emitir_certidao_negativa": False}]})
    r = await cnd.consultar_cnd("51260859000170", client)
    assert r["status"] == cnd.POSITIVA


async def test_consultar_cnd_code_erro_vira_falha():
    client = _FakeClient({"code": 605, "code_message": "timeout", "data": []})
    r = await cnd.consultar_cnd("51260859000170", client)
    assert r["status"] == cnd.FALHA


async def test_consultar_cnd_excecao_de_rede_vira_falha():
    class _Boom:
        async def post(self, *a, **k):
            raise httpx.ConnectError("boom")

    r = await cnd.consultar_cnd("51260859000170", _Boom())
    assert r["status"] == cnd.FALHA
