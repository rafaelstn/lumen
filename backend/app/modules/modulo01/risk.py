"""Engine de risco 2027 — cruza classificação com status de CND. Fase 4.

A partir de 2027, empresas inadimplentes não poderão transferir crédito de ICMS.
Fornecedor que oferece crédito hoje (Grupo A) mas tem débito ativo é risco ALTO.
"""
from decimal import Decimal, ROUND_HALF_UP

from app.modules.modulo01 import cnd

ALTO = "ALTO"
MEDIO = "MEDIO"
BAIXO = "BAIXO"


def _impacto_anual(total_compras, aliquota_max) -> float:
    """Estimativa do crédito anual em risco = compras * alíquota / 100 (Decimal, 2 casas)."""
    compras = Decimal(str(total_compras or 0))
    aliq = Decimal(str(aliquota_max or 0))
    valor = (compras * aliq / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(valor)


def aplicar_risco(fornecedores: list[dict]) -> None:
    """Adiciona risco_2027, motivo_risco e impacto_financeiro_anual a cada fornecedor (in-place)."""
    for f in fornecedores:
        grupo = f.get("grupo")
        status = f.get("status_cnd")
        impacto = _impacto_anual(f.get("total_compras"), f.get("aliquota_max"))

        # Risco restrito ao Grupo A (crédito pleno 12/18%): é onde a perda de crédito
        # em 2027 é financeiramente relevante. Grupo B (crédito simbólico <10%) e C
        # (sem crédito) não entram no alerta.
        if grupo == "A" and status in (cnd.POSITIVA, cnd.POSITIVA_EFEITO_NEGATIVA):
            risco, motivo = ALTO, (
                "Oferece crédito de ICMS hoje, mas possui débito ativo na Receita. "
                "A partir de 2027, inadimplentes não poderão transferir crédito."
            )
        elif grupo == "A" and status == cnd.FALHA:
            risco, motivo = MEDIO, "Não foi possível verificar a regularidade fiscal."
        else:
            risco, motivo = BAIXO, ""

        f["risco_2027"] = risco
        f["motivo_risco"] = motivo
        f["impacto_financeiro_anual"] = impacto


def alertas_ordenados(fornecedores: list[dict]) -> list[dict]:
    """Lista os fornecedores de risco ALTO ordenados por impacto financeiro decrescente."""
    altos = [f for f in fornecedores if f.get("risco_2027") == ALTO]
    return sorted(altos, key=lambda f: f.get("impacto_financeiro_anual", 0), reverse=True)
