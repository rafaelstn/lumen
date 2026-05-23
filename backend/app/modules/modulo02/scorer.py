"""Engine de score fiscal 0-100 (Módulo 02). Função pura, testável.

Compõe o score a partir de sinais públicos do fornecedor. Quanto maior, melhor
(menor risco de perda de crédito). Heurística documentada — ajustável conforme
o mercado validar (não é premissa fixa).
"""
from datetime import date, datetime

# Pesos por componente (somam 100 no melhor caso).
_CND = {"NEGATIVA": 35, "POSITIVA_EFEITO_NEGATIVA": 18, "POSITIVA": 0, "FALHA": 8}


def _anos_desde(fundacao: str | None) -> float | None:
    if not fundacao:
        return None
    try:
        d = datetime.fromisoformat(str(fundacao)[:10]).date()
    except ValueError:
        return None
    return (date.today() - d).days / 365.25


def calcular_score(
    *,
    simples_optante: bool | None,
    situacao_cadastral: str | None,
    status_cnd: str | None,
    fundacao: str | None,
) -> dict:
    componentes: dict[str, int] = {}

    # Regime tributário: Lucro Real/Presumido (não optante do Simples) gera crédito pleno.
    if simples_optante is False:
        componentes["regime"] = 30
    elif simples_optante is True:
        componentes["regime"] = 15
    else:
        componentes["regime"] = 10  # indeterminado

    # Situação cadastral na Receita.
    sit = (situacao_cadastral or "").upper()
    if "ATIVA" in sit:
        componentes["situacao_cadastral"] = 25
    elif "SUSPENSA" in sit:
        componentes["situacao_cadastral"] = 10
    else:
        componentes["situacao_cadastral"] = 0  # Inapta/Baixada/desconhecida

    # Regularidade fiscal (CND).
    componentes["cnd"] = _CND.get(status_cnd or "", 8)

    # Maturidade do CNPJ (< 2 anos = risco maior).
    anos = _anos_desde(fundacao)
    componentes["maturidade"] = 10 if (anos is not None and anos >= 2) else 0

    score = max(0, min(100, sum(componentes.values())))
    faixa = "BAIXO" if score >= 70 else "MEDIO" if score >= 40 else "ALTO"
    return {"score": score, "faixa": faixa, "componentes": componentes}
