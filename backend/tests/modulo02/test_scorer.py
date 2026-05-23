"""Testes da engine de score fiscal (Módulo 02), função pura."""
from datetime import date

from app.modules.modulo02 import scorer


def test_fornecedor_ideal_score_alto():
    r = scorer.calcular_score(
        simples_optante=False,            # Lucro Real/Presumido
        situacao_cadastral="Ativa",
        status_cnd="NEGATIVA",
        fundacao="2010-01-01",
    )
    assert r["score"] == 100
    assert r["faixa"] == "BAIXO"


def test_fornecedor_irregular_score_baixo():
    r = scorer.calcular_score(
        simples_optante=True,             # Simples
        situacao_cadastral="Inapta",
        status_cnd="POSITIVA",            # débito ativo
        fundacao="2025-06-01",            # < 2 anos
    )
    # regime 15 + situacao 0 + cnd 0 + maturidade 0 = 15
    assert r["score"] == 15
    assert r["faixa"] == "ALTO"


def test_faixas():
    assert scorer.calcular_score(simples_optante=False, situacao_cadastral="Ativa", status_cnd="POSITIVA_EFEITO_NEGATIVA", fundacao="2000-01-01")["faixa"] == "BAIXO"
    # regime 15 + situacao 25 + cnd 8(FALHA) + maturidade 10 = 58 → MEDIO
    assert scorer.calcular_score(simples_optante=True, situacao_cadastral="Ativa", status_cnd="FALHA", fundacao="2000-01-01")["faixa"] == "MEDIO"


def test_score_nunca_passa_de_100_nem_abaixo_de_0():
    r = scorer.calcular_score(simples_optante=False, situacao_cadastral="Ativa", status_cnd="NEGATIVA", fundacao="1990-01-01")
    assert 0 <= r["score"] <= 100
