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


async def avaliar_cnpj(
    cnpj: str, client: httpx.AsyncClient, throttle=None, incluir_cnd: bool = True
) -> dict:
    """Consulta dados cadastrais (+ CND opcional) e devolve o score fiscal do fornecedor.

    Em lote, passe um throttle (cnpj_lookup.novo_throttle()) para respeitar o rate do plano.
    Rate limit (RateLimitError) e crédito esgotado propagam para o chamador parar o lote ANTES
    de gastar a CND (que é consulta paga separada). Falha pontual de dado vira score sem CNPJá.

    incluir_cnd=False: avalia SÓ o cadastro (não consulta a Infosimples, não consome crédito de
    CND, não exige token). O score fica parcial (sem o componente de regularidade) e status_cnd
    volta None ("não consultado"). origem_fora fica False (não houve consulta à fonte).
    """
    try:
        dados = await cnpj_lookup.consultar_cnpj(cnpj, client, throttle=throttle)
    except cnpj_lookup.RateLimitError:
        raise  # transitório: o chamador para o lote e pede para aguardar
    except cnpj_lookup.LookupError as exc:
        if "rédit" in str(exc):  # crédito real esgotado: para o lote (definitivo)
            raise
        dados = {}  # falha pontual de dado: segue com score parcial

    cnd_res = await cnd.consultar_cnd(cnpj, client) if incluir_cnd else None

    # Grava o cadastro completo do CNPJ (veio no mesmo retorno da consulta, sem crédito extra)
    # e registra o metadado de CND. Tudo tolerante: banco fora não derruba a avaliação.
    if cnpj:
        try:
            async with async_session_factory() as session:
                cadastro = dados.get("cadastro")
                if cadastro and cadastro.get("cnpj"):
                    await fornecedores_repo.salvar_cadastro(session, cadastro, "cnpja")
                # Metadado de controle da última CND (não fonte de verdade). Só com status real:
                # FALHA não atualiza a data, para não mascarar o que é recente. Sem CND
                # (cnd_res None) não há metadado a registrar.
                if cnd_res is not None and cnd_res["status"] != cnd.FALHA:
                    await fornecedores_repo.registrar_cnd(
                        session, cnpj, cnd_res["status"], razao_social=dados.get("nome_oficial")
                    )
        except Exception:
            logger.warning("M02: falha ao gravar cadastro/metadado de CND por CNPJ.", exc_info=True)

    status_cnd = cnd_res["status"] if cnd_res is not None else None
    s = scorer.calcular_score(
        simples_optante=dados.get("simples_optante"),
        situacao_cadastral=dados.get("situacao_cadastral"),
        status_cnd=status_cnd,
        fundacao=dados.get("fundacao"),
        incluir_cnd=incluir_cnd,
    )
    return {
        "cnpj": cnpj,
        "razao_social": dados.get("nome_oficial"),
        "situacao_cadastral": dados.get("situacao_cadastral"),
        "simples_optante": dados.get("simples_optante"),
        "status_cnd": status_cnd,  # None quando incluir_cnd=False (não consultado)
        # Sinaliza que a CND falhou por a FONTE (Receita/PGFN) estar fora do ar. False quando
        # não houve consulta de CND (incluir_cnd=False) ou quando a fonte respondeu normal.
        "origem_fora": bool(cnd_res.get("origem_fora")) if cnd_res is not None else False,
        # Requisição faturada pela Infosimples (header.billable). Inclui falhas que cobram (611...).
        # É o que alimenta o audit trail de custo, não "status != FALHA".
        "cobrada": bool(cnd_res.get("cobrada")) if cnd_res is not None else False,
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
    consultas_cnpj, cnds_cobradas = 0, 0

    throttle = cnpj_lookup.novo_throttle()
    async with httpx.AsyncClient() as client:
        for f in monitorados:
            # Reserva atômica do teto (não check-then-consume): só consulta a API paga se
            # houver saldo no momento da reserva. Sob concorrência, restante pode zerar entre
            # o check e o consumir (TOCTOU). Se faltar saldo, estorna o que já reservei.
            if not budget.consumir("cnd"):
                teto_atingido = True
                break
            if not budget.consumir("cnpj"):
                budget.devolver("cnd")
                teto_atingido = True
                break
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
            if avaliacao.get("cobrada"):
                cnds_cobradas += 1

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
            consultas_cobradas=cnds_cobradas, contexto=f"{reavaliados} monitorado(s)",
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
