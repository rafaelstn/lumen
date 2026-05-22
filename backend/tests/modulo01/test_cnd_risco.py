"""Testes do mapeamento de CND e da engine de risco 2027 (puros, sem chamar a API)."""
from app.modules.modulo01 import cnd, risk


def test_mapeamento_status_cnd():
    assert cnd._mapear_status({"conseguiu_emitir_certidao_negativa": True}) == cnd.NEGATIVA
    assert cnd._mapear_status({"conseguiu_emitir_certidao_negativa": False}) == cnd.POSITIVA
    # Conseguiu emitir, mas há débitos (parcelados) → positiva com efeito de negativa.
    assert (
        cnd._mapear_status({"conseguiu_emitir_certidao_negativa": True, "debitos_pgfn": [{"x": 1}]})
        == cnd.POSITIVA_EFEITO_NEGATIVA
    )


def test_risco_grupo_a_com_debito_e_alto():
    fornecedores = [
        {"grupo": "A", "status_cnd": cnd.POSITIVA, "total_compras": 100000.0, "aliquota_max": 18.0},
        {"grupo": "A", "status_cnd": cnd.NEGATIVA, "total_compras": 50000.0, "aliquota_max": 12.0},
        {"grupo": "A", "status_cnd": cnd.FALHA, "total_compras": 10000.0, "aliquota_max": 18.0},
        {"grupo": "C", "status_cnd": cnd.POSITIVA, "total_compras": 30000.0, "aliquota_max": 0.0},
    ]
    risk.aplicar_risco(fornecedores)
    assert fornecedores[0]["risco_2027"] == risk.ALTO
    assert fornecedores[0]["impacto_financeiro_anual"] == 18000.00
    assert fornecedores[1]["risco_2027"] == risk.BAIXO
    assert fornecedores[2]["risco_2027"] == risk.MEDIO
    assert fornecedores[3]["risco_2027"] == risk.BAIXO  # grupo C não gera crédito relevante


def test_alertas_ordenados_por_impacto():
    fornecedores = [
        {"grupo": "A", "status_cnd": cnd.POSITIVA, "total_compras": 10000.0, "aliquota_max": 18.0},
        {"grupo": "A", "status_cnd": cnd.POSITIVA, "total_compras": 100000.0, "aliquota_max": 18.0},
    ]
    risk.aplicar_risco(fornecedores)
    alertas = risk.alertas_ordenados(fornecedores)
    assert len(alertas) == 2
    assert alertas[0]["impacto_financeiro_anual"] >= alertas[1]["impacto_financeiro_anual"]
