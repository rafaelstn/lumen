"""Orquestração do Módulo 02: avalia um CNPJ (dados cadastrais + CND) e calcula o score.

Cada avaliação consome consultas pagas (CNPJá para dados/Simples/fundação + Infosimples
para a CND). O controle de orçamento e o teto por chamada ficam no router.
"""
import logging

import httpx

from app.database import async_session_factory
from app.modules.consumo import repo as consumo_repo
from app.modules.modulo01 import budget, cnd, cnpj_lookup, fornecedores_repo
from app.modules.modulo02 import repo, scorer

logger = logging.getLogger("modulo02")


async def avaliar_cnpj(cnpj: str, client: httpx.AsyncClient, throttle=None) -> dict:
    """Consulta dados cadastrais + CND e devolve o score fiscal do fornecedor.

    Em lote, passe um throttle (cnpj_lookup.novo_throttle()) para respeitar o rate do plano.
    Rate limit (RateLimitError) e crédito esgotado propagam para o chamador parar o lote ANTES
    de gastar a CND (que é consulta paga separada). Falha pontual de dado vira score sem CNPJá.
    """
    try:
        dados = await cnpj_lookup.consultar_cnpj(cnpj, client, throttle=throttle)
    except cnpj_lookup.RateLimitError:
        raise  # transitório: o chamador para o lote e pede para aguardar
    except cnpj_lookup.LookupError as exc:
        if "rédit" in str(exc):  # crédito real esgotado: para o lote (definitivo)
            raise
        dados = {}  # falha pontual de dado: segue com score parcial

    cnd_res = await cnd.consultar_cnd(cnpj, client)

    # Registra por CNPJ quando/qual foi a última CND (metadado de controle, não fonte de verdade).
    # Só com status real: FALHA não atualiza a data. Tolerante: banco fora não derruba a avaliação.
    if cnpj and cnd_res["status"] != cnd.FALHA:
        try:
            async with async_session_factory() as session:
                await fornecedores_repo.registrar_cnd(
                    session, cnpj, cnd_res["status"], razao_social=dados.get("nome_oficial")
                )
        except Exception:
            logger.warning("M02: falha ao registrar metadado de CND por CNPJ.", exc_info=True)

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
    limite_taxa_atingido = False
    consultas_cnpj, cnds_concluidas = 0, 0

    throttle = cnpj_lookup.novo_throttle()
    async with httpx.AsyncClient() as client:
        for f in monitorados:
            if budget.restante("cnd") <= 0 or budget.restante("cnpj") <= 0:
                teto_atingido = True
                break
            budget.consumir("cnd")
            budget.consumir("cnpj")
            status_anterior = f.status_cnd_atual
            try:
                avaliacao = await service_avaliar(client, f.cnpj, throttle)
            except cnpj_lookup.LookupError as exc:
                # Rate limit (RateLimitError) ou crédito esgotado: a CND deste item não rodou.
                # Estorna ambos e para a reavaliação preservando o que já foi atualizado.
                budget.devolver("cnpj")
                budget.devolver("cnd")
                limite_taxa_atingido = isinstance(exc, cnpj_lookup.RateLimitError)
                break
            await repo.upsert_monitorado(session, escritorio_id, avaliacao)
            reavaliados += 1
            consultas_cnpj += 1
            if avaliacao.get("status_cnd") and avaliacao["status_cnd"] != "FALHA":
                cnds_concluidas += 1

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

    # Audit trail do consumo da reavaliação. Resiliente: o gasto na API já ocorreu.
    try:
        await consumo_repo.registrar_cnpj(
            escritorio_id=escritorio_id, modulo="modulo02", operacao="reavaliacao",
            consultas=consultas_cnpj, contexto=f"{reavaliados} monitorado(s)",
        )
        await consumo_repo.registrar_cnd(
            escritorio_id=escritorio_id, modulo="modulo02", operacao="reavaliacao",
            consultas_concluidas=cnds_concluidas, contexto=f"{reavaliados} monitorado(s)",
        )
    except Exception:
        import logging
        logging.getLogger("modulo02").warning("Falha ao registrar consumo da reavaliação.", exc_info=True)

    return {
        "reavaliados": reavaliados,
        "alertas_gerados": alertas,
        "teto_atingido": teto_atingido,
        "limite_taxa_atingido": limite_taxa_atingido,
    }


async def service_avaliar(client, cnpj, throttle=None):
    return await avaliar_cnpj(cnpj, client, throttle=throttle)
