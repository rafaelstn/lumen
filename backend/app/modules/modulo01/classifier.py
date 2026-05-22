"""Engine de classificação de fornecedores nos grupos A/B/C. Fase 2.

Regras (sobre aliquota_max do fornecedor):
- Grupo A: aliquota_max >= 12  → crédito pleno (Lucro Real/Presumido)
- Grupo B: 0 < aliquota_max < 10 → crédito simbólico (Simples Nacional)
- Grupo C: aliquota_max == 0    → sem crédito (Simples Nacional)

Caso especial: aliquota_max >= 12 e ICMS efetivo zerado → Grupo A com flag
verificar_st (possível Substituição Tributária ou erro de lançamento).
"""
from decimal import Decimal, ROUND_HALF_UP

import pandas as pd

# Alíquota de referência para estimar o crédito que o cliente deixou de aproveitar
# ao comprar de fornecedor do Simples (Grupo C), caso comprasse de um Lucro Real.
# A fórmula literal do briefing usa aliquota_max, que é 0 no Grupo C; usamos esta
# referência (alíquota interna padrão de SP) por ser o que dá sentido ao número.
ALIQUOTA_REFERENCIA_CREDITO_PERDIDO = Decimal("18")

LABELS = {
    "A": "Bom — Lucro Real/Presumido",
    "B": "Crédito Podre — Simples Nacional",
    "C": "Sem Crédito — Simples Nacional",
    "INDEFINIDO": "Indefinido — alíquota 10–12% requer revisão de regra",
}


def _grupo(aliquota_max: Decimal) -> str:
    if aliquota_max >= Decimal("12"):
        return "A"
    if Decimal("0") < aliquota_max < Decimal("10"):
        return "B"
    if aliquota_max == Decimal("0"):
        return "C"
    # Faixa [10, 12): não é A, B nem C. Não pode ser mascarada como "sem crédito" —
    # regra de negócio pendente. Sinaliza para revisão em vez de distorcer o número.
    return "INDEFINIDO"


def classificar(df: pd.DataFrame) -> pd.DataFrame:
    """Adiciona grupo, label, flags e métricas de crédito a cada fornecedor."""
    grupos, labels, verificar_st = [], [], []
    credito_aproveitado, credito_perdido = [], []

    for _, f in df.iterrows():
        aliquota_max = f["aliquota_max"]
        icms = f["total_valor_icms"]
        compras = f["total_compras"]

        grupo = _grupo(aliquota_max)
        label = LABELS[grupo]

        # Caso especial: alíquota cheia mas ICMS zerado (possível ST).
        st = grupo == "A" and icms == Decimal("0.00")
        if st:
            label = f"{label} | Atenção: possível Substituição Tributária"

        # Crédito perdido só faz sentido para o Grupo C (comprou sem crédito).
        # Clamp em 0: estorno pode tornar total_compras negativo e crédito perdido
        # negativo não tem sentido fiscal.
        if grupo == "C" and compras > Decimal("0"):
            perdido = (compras * ALIQUOTA_REFERENCIA_CREDITO_PERDIDO / Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        else:
            perdido = Decimal("0.00")

        grupos.append(grupo)
        labels.append(label)
        verificar_st.append(st)
        credito_aproveitado.append(icms)
        credito_perdido.append(perdido)

    out = df.copy()
    out["grupo"] = grupos
    out["label"] = labels
    out["verificar_st"] = verificar_st
    out["credito_aproveitado"] = credito_aproveitado
    out["credito_perdido"] = credito_perdido
    return out
