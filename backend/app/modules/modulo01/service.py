"""Orquestra o pipeline da Fase 2: parser → merge → classificação → resumo.

Mantém a lógica de negócio fora do router. Converte Decimal para float apenas
na borda de saída (a precisão Decimal é preservada em todo o cálculo interno).
"""
from decimal import Decimal

import pandas as pd

from app.modules.modulo01 import classifier, parser

_ORDEM_GRUPO = {"A": 0, "B": 1, "C": 2, "INDEFINIDO": 3}


def _result(row: pd.Series) -> dict:
    return {
        "cod_forn": row["cod_forn"],
        "nome_forn": row["nome_forn"],
        "cnpj": row["cnpj"],
        "cnpj_pendente": bool(row["cnpj_pendente"]),
        "cnpj_nao_casado": bool(row.get("cnpj_nao_casado", False)),
        "cnpj_confirmado": bool(row.get("cnpj_confirmado", False)),
        "grupo": row["grupo"],
        "label": row["label"],
        "verificar_st": bool(row["verificar_st"]),
        "tem_estorno": bool(row.get("tem_estorno", False)),
        "total_compras": float(row["total_compras"]),
        "total_valor_icms": float(row["total_valor_icms"]),
        "aliquota_max": float(row["aliquota_max"]),
        "aliquota_efetiva_pct": float(row["aliquota_efetiva_pct"]),
        "credito_aproveitado": float(row["credito_aproveitado"]),
        "credito_perdido": float(row["credito_perdido"]),
        "n_lancamentos": int(row["n_lancamentos"]),
    }


def _resumo(df: pd.DataFrame) -> dict:
    credito = sum((v for v in df["credito_aproveitado"]), Decimal("0.00"))
    compras_sem_credito = sum(
        (v for v in df.loc[df["grupo"] == "C", "total_compras"]), Decimal("0.00")
    )
    return {
        "total_fornecedores": int(len(df)),
        "grupo_a": int((df["grupo"] == "A").sum()),
        "grupo_b": int((df["grupo"] == "B").sum()),
        "grupo_c": int((df["grupo"] == "C").sum()),
        "grupo_indefinido": int((df["grupo"] == "INDEFINIDO").sum()),
        "caso_especial": int(df["verificar_st"].sum()),
        "total_credito_aproveitado": float(credito),
        "total_compras_sem_credito": float(compras_sem_credito),
        "cnpj_casados": int((~df["cnpj_pendente"]).sum()),
        "cnpj_pendentes": int(df["cnpj_pendente"].sum()),
    }


def processar(entradas_path: str, cadastro_path: str | None = None) -> tuple[dict, list[dict]]:
    df_entradas = parser.parse_entradas(entradas_path)
    df_cadastro = parser.parse_cadastro(cadastro_path) if cadastro_path else None
    merged = parser.merge_fornecedores(df_entradas, df_cadastro)
    classified = classifier.classificar(merged)

    classified = classified.sort_values(
        by=["grupo", "total_compras"],
        key=lambda col: col.map(_ORDEM_GRUPO) if col.name == "grupo" else col,
        ascending=[True, False],
    )

    fornecedores = [_result(row) for _, row in classified.iterrows()]
    return _resumo(classified), fornecedores
