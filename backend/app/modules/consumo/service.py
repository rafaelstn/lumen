"""Lógica de negócio do consumo: agregação do histórico por período.

Funções puras de agregação (testáveis sem banco) + orquestração de leitura.
Soma em centavos inteiros: sem perda de precisão (financeiro.md).
"""
from collections import defaultdict
from datetime import datetime
from typing import Sequence

from app.modules.consumo.models import ConsultaLog


def agregar_por_periodo(logs: Sequence[ConsultaLog]) -> dict:
    """Totaliza créditos e custo (centavos) e agrupa por dia e por mês.

    Tudo inteiro: soma de centavos não perde fração. Ordena os períodos do mais recente
    para o mais antigo (alinha com a lista de itens).
    """
    total_creditos = 0
    total_custo = 0
    por_dia: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # chave -> [creditos, custo]
    por_mes: dict[str, list[int]] = defaultdict(lambda: [0, 0])

    for log in logs:
        total_creditos += log.creditos_consumidos
        total_custo += log.custo_centavos
        dia = log.criado_em.strftime("%Y-%m-%d")
        mes = log.criado_em.strftime("%Y-%m")
        por_dia[dia][0] += log.creditos_consumidos
        por_dia[dia][1] += log.custo_centavos
        por_mes[mes][0] += log.creditos_consumidos
        por_mes[mes][1] += log.custo_centavos

    def _serie(d: dict[str, list[int]]) -> list[dict]:
        return [
            {"periodo": k, "creditos_consumidos": v[0], "custo_centavos": v[1]}
            for k, v in sorted(d.items(), reverse=True)
        ]

    return {
        "totais": {"creditos_consumidos": total_creditos, "custo_centavos": total_custo},
        "por_dia": _serie(por_dia),
        "por_mes": _serie(por_mes),
    }


def montar_historico(logs: Sequence[ConsultaLog]) -> dict:
    """Monta o payload completo do histórico (itens + totais + séries por período)."""
    agregado = agregar_por_periodo(logs)
    itens = [
        {
            "id": log.id,
            "criado_em": log.criado_em,
            "modulo": log.modulo,
            "servico": log.servico,
            "operacao": log.operacao,
            "quantidade": log.quantidade,
            "creditos_consumidos": log.creditos_consumidos,
            "preco_unitario_centavos": log.preco_unitario_centavos,
            "custo_centavos": log.custo_centavos,
            "consumo_estimado": log.consumo_estimado,
            "contexto": log.contexto,
        }
        for log in logs
    ]
    return {"itens": itens, **agregado}


def parse_data(valor: str | None) -> datetime | None:
    """Converte 'YYYY-MM-DD' ou ISO 8601 em datetime. None se vazio. Lança ValueError se inválido."""
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor)
    except ValueError as exc:
        raise ValueError(f"Data inválida: {valor!r}. Use YYYY-MM-DD ou ISO 8601.") from exc
