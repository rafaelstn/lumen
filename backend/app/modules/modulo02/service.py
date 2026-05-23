"""Orquestração do Módulo 02: avalia um CNPJ (dados cadastrais + CND) e calcula o score.

Cada avaliação consome consultas pagas (CNPJá para dados/Simples/fundação + Infosimples
para a CND). O controle de orçamento e o teto por chamada ficam no router.
"""
import httpx

from app.modules.modulo01 import cnd, cnpj_lookup
from app.modules.modulo02 import scorer


async def avaliar_cnpj(cnpj: str, client: httpx.AsyncClient) -> dict:
    """Consulta dados cadastrais + CND e devolve o score fiscal do fornecedor."""
    try:
        dados = await cnpj_lookup.consultar_cnpj(cnpj, client)
    except cnpj_lookup.LookupError:
        dados = {}

    cnd_res = await cnd.consultar_cnd(cnpj, client)

    s = scorer.calcular_score(
        simples_optante=dados.get("simples_optante"),
        situacao_cadastral=dados.get("situacao_cadastral"),
        status_cnd=cnd_res["status"],
        fundacao=dados.get("fundacao"),
    )
    return {
        "cnpj": cnpj,
        "razao_social": dados.get("nome_oficial"),
        "situacao_cadastral": dados.get("situacao_cadastral"),
        "simples_optante": dados.get("simples_optante"),
        "status_cnd": cnd_res["status"],
        "score": s["score"],
        "faixa": s["faixa"],
        "componentes": s["componentes"],
    }
