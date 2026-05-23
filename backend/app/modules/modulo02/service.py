"""Orquestração do Módulo 02: avalia um CNPJ (dados cadastrais + CND) e calcula o score.

Cada avaliação consome consultas pagas (CNPJá para dados/Simples/fundação + Infosimples
para a CND). O controle de orçamento e o teto por chamada ficam no router.
"""
import httpx

from app.modules.modulo01 import budget, cnd, cnpj_lookup
from app.modules.modulo02 import repo, scorer


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


async def reavaliar_carteira(session, escritorio_id: str) -> dict:
    """Re-avalia os fornecedores monitorados, grava histórico e gera alertas em mudança.

    Respeita o teto de orçamento (para quando os créditos do dia acabam). É o núcleo do
    monitoramento contínuo (chamado pelo scheduler ou sob demanda).
    """
    monitorados = await repo.listar_monitorados(session, escritorio_id)
    reavaliados, alertas, teto_atingido = 0, 0, False

    async with httpx.AsyncClient() as client:
        for f in monitorados:
            if budget.restante("cnd") <= 0 or budget.restante("cnpj") <= 0:
                teto_atingido = True
                break
            budget.consumir("cnd")
            budget.consumir("cnpj")
            status_anterior = f.status_cnd_atual
            avaliacao = await service_avaliar(client, f.cnpj)
            await repo.upsert_monitorado(session, escritorio_id, avaliacao)
            reavaliados += 1

            if status_anterior and status_anterior != avaliacao["status_cnd"]:
                await repo.criar_alerta(
                    session, escritorio_id, f.id, "MUDANCA_STATUS",
                    f"{avaliacao.get('razao_social') or f.cnpj}: CND mudou de {status_anterior} para {avaliacao['status_cnd']}.",
                )
                alertas += 1
            elif avaliacao["faixa"] == "ALTO":
                await repo.criar_alerta(
                    session, escritorio_id, f.id, "SCORE_CRITICO",
                    f"{avaliacao.get('razao_social') or f.cnpj}: score {avaliacao['score']} (risco alto).",
                )
                alertas += 1

    return {"reavaliados": reavaliados, "alertas_gerados": alertas, "teto_atingido": teto_atingido}


async def service_avaliar(client, cnpj):
    return await avaliar_cnpj(cnpj, client)
