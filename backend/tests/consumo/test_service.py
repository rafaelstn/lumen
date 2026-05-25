"""Testes de agregação do histórico (função pura, sem banco)."""
from datetime import datetime, timezone

import pytest

from app.modules.consumo import service
from app.modules.consumo.models import ConsultaLog


def _log(dt: datetime, creditos: int, custo: int) -> ConsultaLog:
    return ConsultaLog(
        criado_em=dt, modulo="modulo01", servico="cnpj", operacao="x",
        quantidade=1, creditos_consumidos=creditos, preco_unitario_centavos=2,
        custo_centavos=custo, consumo_estimado=True,
    )


def test_agregacao_totais_e_periodos():
    logs = [
        _log(datetime(2026, 5, 25, 10, tzinfo=timezone.utc), 2, 5),
        _log(datetime(2026, 5, 25, 14, tzinfo=timezone.utc), 2, 5),
        _log(datetime(2026, 5, 24, 9, tzinfo=timezone.utc), 4, 10),
        _log(datetime(2026, 4, 30, 9, tzinfo=timezone.utc), 1, 26),
    ]
    r = service.agregar_por_periodo(logs)
    assert r["totais"]["creditos_consumidos"] == 9
    assert r["totais"]["custo_centavos"] == 46

    # Por dia, ordenado do mais recente para o mais antigo.
    dias = {p["periodo"]: p for p in r["por_dia"]}
    assert dias["2026-05-25"]["creditos_consumidos"] == 4
    assert dias["2026-05-25"]["custo_centavos"] == 10
    assert dias["2026-05-24"]["custo_centavos"] == 10
    assert r["por_dia"][0]["periodo"] == "2026-05-25"

    # Por mês.
    meses = {p["periodo"]: p for p in r["por_mes"]}
    assert meses["2026-05"]["custo_centavos"] == 20
    assert meses["2026-04"]["custo_centavos"] == 26


def test_agregacao_vazia():
    r = service.agregar_por_periodo([])
    assert r["totais"] == {"creditos_consumidos": 0, "custo_centavos": 0}
    assert r["por_dia"] == [] and r["por_mes"] == []


def test_parse_data():
    assert service.parse_data(None) is None
    assert service.parse_data("") is None
    assert service.parse_data("2026-05-25").year == 2026
    with pytest.raises(ValueError):
        service.parse_data("25/05/2026")
