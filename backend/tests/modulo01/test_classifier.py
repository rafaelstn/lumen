"""Testes da engine de classificação, validados contra o arquivo real."""
from decimal import Decimal

import pandas as pd

from app.modules.modulo01 import classifier, parser


def _classificado(idesan_xls):
    df = parser.parse_entradas(idesan_xls)
    merged = parser.merge_fornecedores(df)
    return classifier.classificar(merged)


def test_distribuicao_dos_grupos(idesan_xls):
    df = _classificado(idesan_xls)
    assert (df["grupo"] == "A").sum() == 35
    assert (df["grupo"] == "B").sum() == 7
    assert (df["grupo"] == "C").sum() == 15
    assert len(df) == 57


def test_metal_cut_e_caso_especial_st(idesan_xls):
    df = _classificado(idesan_xls)
    metal = df[df["nome_forn"].str.contains("METAL CUT", case=False)]
    assert len(metal) == 1
    linha = metal.iloc[0]
    assert linha["grupo"] == "A"  # alíquota 18%
    assert bool(linha["verificar_st"]) is True
    assert linha["total_valor_icms"] == Decimal("0.00")
    assert "Substituição Tributária" in linha["label"]


def test_grupo_c_tem_credito_perdido_estimado(idesan_xls):
    df = _classificado(idesan_xls)
    grupo_c = df[df["grupo"] == "C"]
    # Crédito perdido = compras * 18% de referência (todos > 0).
    assert (grupo_c["credito_perdido"] > Decimal("0")).all()
    esperado = (grupo_c.iloc[0]["total_compras"] * Decimal("18") / Decimal("100")).quantize(
        Decimal("0.01")
    )
    assert grupo_c.iloc[0]["credito_perdido"] == esperado


def test_grupos_nao_c_nao_tem_credito_perdido(idesan_xls):
    df = _classificado(idesan_xls)
    assert (df[df["grupo"] != "C"]["credito_perdido"] == Decimal("0.00")).all()


def _linha(aliq, icms="1.00", compras="100.00"):
    return {
        "nome_forn": "X",
        "aliquota_max": Decimal(aliq),
        "total_valor_icms": Decimal(icms),
        "total_compras": Decimal(compras),
    }


def test_regras_de_grupo_isoladas():
    df = pd.DataFrame([_linha("18"), _linha("12"), _linha("3.50"), _linha("0", "0.00")])
    out = classifier.classificar(df)
    assert list(out["grupo"]) == ["A", "A", "B", "C"]


def test_bordas_das_aliquotas():
    # 12 exato → A; 9.99 → B; 10 e 11.99 → INDEFINIDO (não pode virar C); 0 → C.
    df = pd.DataFrame(
        [_linha("12.00"), _linha("9.99"), _linha("10.00"), _linha("11.99"), _linha("0", "0.00")]
    )
    out = classifier.classificar(df)
    assert list(out["grupo"]) == ["A", "B", "INDEFINIDO", "INDEFINIDO", "C"]


def test_faixa_indefinida_nao_gera_credito_perdido():
    df = pd.DataFrame([_linha("11.00", icms="0.00", compras="1000.00")])
    out = classifier.classificar(df)
    assert out.iloc[0]["grupo"] == "INDEFINIDO"
    assert out.iloc[0]["credito_perdido"] == Decimal("0.00")


def test_credito_perdido_nunca_negativo_com_estorno():
    # Grupo C com compras negativas (estorno dominante) → crédito perdido clampado em 0.
    df = pd.DataFrame([_linha("0", icms="0.00", compras="-500.00")])
    out = classifier.classificar(df)
    assert out.iloc[0]["grupo"] == "C"
    assert out.iloc[0]["credito_perdido"] == Decimal("0.00")
