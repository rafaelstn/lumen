"""Endpoints do Módulo 02 — Score Fiscal e monitoramento de fornecedores.

Consultas pagas (CNPJá + Infosimples) protegidas por teto de orçamento + clamp.
Tenant pelo escritório atual (single-tenant no MVP via escritorio_atual).
"""
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth.deps import Contexto, contexto_atual
from app.config import settings
from app.database import async_session_factory
from app.modules.consumo import repo as consumo_repo
from app.modules.modulo01 import budget, cnpj_lookup, fornecedores_repo
from app.modules.modulo02 import repo, service
from app.modules.modulo02.schemas import DueDiligenceIn, MonitorarIn
from app.ratelimit import limiter

router = APIRouter()


@router.get("/status")
async def status():
    return {"modulo": "02", "nome": "Score Fiscal de Fornecedores", "status": "ok"}


def _normalizar_cnpjs(cnpjs: list[str]) -> list[str]:
    validos = []
    for c in cnpjs:
        d = re.sub(r"[^0-9A-Za-z]", "", c or "").upper()
        if cnpj_lookup.validar_cnpj(d):
            validos.append(d)
    return validos


async def _associar(escritorio_id: str, cnpjs: list[str]) -> None:
    """Registra a associação escritório <-> CNPJ avaliado (visão isolada). Tolerante a falha."""
    cnpjs = [c for c in {c for c in cnpjs if c}]
    if not escritorio_id or not cnpjs:
        return
    try:
        async with async_session_factory() as session:
            for cnpj in cnpjs:
                await fornecedores_repo.associar_escritorio(session, escritorio_id, cnpj)
    except Exception:
        import logging
        logging.getLogger("modulo02").warning(
            "Falha ao associar fornecedor(es) ao escritório.", exc_info=True
        )


async def _registrar_consumo(
    escritorio: str, modulo: str, operacao: str,
    consultas_cnpj: int, cnds_cobradas: int, contexto: str | None,
) -> None:
    """Grava o audit trail do consumo (CNPJ + CND). Resiliente: nunca derruba a operação.

    O custo na API externa já ocorreu; falhar o log não pode invalidar a resposta ao usuário.
    A inconsistência fica registrada para reconciliação.
    """
    try:
        await consumo_repo.registrar_cnpj(
            escritorio_id=escritorio, modulo=modulo, operacao=operacao,
            consultas=consultas_cnpj, contexto=contexto,
        )
        await consumo_repo.registrar_cnd(
            escritorio_id=escritorio, modulo=modulo, operacao=operacao,
            consultas_cobradas=cnds_cobradas, contexto=contexto,
        )
    except Exception:
        import logging
        logging.getLogger("modulo02").warning(
            "Falha ao registrar audit trail de consumo (op=%s).", operacao, exc_info=True
        )


@router.post("/due-diligence")
@limiter.limit("4/minute")
async def due_diligence(
    request: Request, body: DueDiligenceIn, ctx: Contexto = Depends(contexto_atual)
):
    """Avalia uma lista de CNPJs (score 0-100) e devolve o ranking (pior primeiro).

    body.incluir_cnd=False avalia só o cadastro (CNPJá): não consulta a CND, não consome o
    crédito de CND, não exige o token da Infosimples e o score sai parcial (sem regularidade).
    """
    incluir_cnd = body.incluir_cnd
    # Token da Infosimples só é exigido quando a CND vai ser consultada.
    if incluir_cnd and not settings.infosimples_token:
        raise HTTPException(status_code=400, detail="Consulta de regularidade (CND) temporariamente indisponível.")

    cnpjs = _normalizar_cnpjs(body.cnpjs)[: settings.cnd_limite_max]
    if not cnpjs:
        raise HTTPException(status_code=422, detail="Nenhum CNPJ válido na lista.")

    resultados = []
    teto_atingido = False
    limite_taxa_atingido = False
    creditos_esgotados = False
    consultas_cnpj = 0          # nº de consultas ao CNPJá (2 créditos cada, estimado)
    cnds_cobradas = 0           # nº de CNDs FATURADAS pela Infosimples (billable; inclui 611/612)
    origem_indisponivel = 0     # nº de CNDs que falharam por a Receita/PGFN estar fora do ar
    throttle = cnpj_lookup.novo_throttle()
    async with httpx.AsyncClient() as client:
        for c in cnpjs:
            # Reserva atômica do teto: só chama a API paga se HOUVER saldo no momento da
            # reserva (consumir devolve False ao estourar). Não basta checar restante>0 antes:
            # sob concorrência o saldo pode zerar entre o check e o consumir (TOCTOU).
            # Sem CND, só reserva o crédito de cadastro (cnpj).
            if incluir_cnd and not budget.consumir("cnd"):
                teto_atingido = True
                break
            if not budget.consumir("cnpj"):
                # cnd já reservada nesta iteração (se incluída); estorna para não inflar contador.
                if incluir_cnd:
                    budget.devolver("cnd")
                teto_atingido = True
                break
            try:
                r = await service.avaliar_cnpj(c, client, throttle=throttle, incluir_cnd=incluir_cnd)
            except cnpj_lookup.RateLimitError:
                # Rate limit no CNPJá: a CND deste item não rodou. Estorna ambos e para o lote.
                budget.devolver("cnpj")
                if incluir_cnd:
                    budget.devolver("cnd")
                limite_taxa_atingido = True
                break
            except cnpj_lookup.LookupError:
                # Crédito real esgotado (avaliar_cnpj só propaga LookupError nesse caso).
                budget.devolver("cnpj")
                if incluir_cnd:
                    budget.devolver("cnd")
                creditos_esgotados = True
                break
            consultas_cnpj += 1
            if r.get("cobrada"):
                cnds_cobradas += 1
            if r.get("origem_fora"):
                origem_indisponivel += 1
            resultados.append(r)

    # Associa ao escritório os CNPJs avaliados (visão isolada do cache global de fornecedores).
    await _associar(ctx.escritorio_id, [r.get("cnpj") for r in resultados if r.get("cnpj")])
    # Audit trail: sem CND, só consome/registra o cadastro (cnpj); cnds_cobradas fica 0.
    await _registrar_consumo(
        ctx.escritorio_id, "modulo02", "due_diligence", consultas_cnpj, cnds_cobradas,
        contexto=f"{len(resultados)} cnpj(s){'' if incluir_cnd else ' (sem cnd)'}",
    )
    resultados.sort(key=lambda r: r["score"])  # pior score primeiro (maior risco)
    return {
        "resultados": resultados,
        "avaliados": len(resultados),
        "incluiu_cnd": incluir_cnd,
        "teto_atingido": teto_atingido,
        "limite_taxa_atingido": limite_taxa_atingido,
        "creditos_esgotados": creditos_esgotados,
        # > 0 sinaliza ao frontend "a Receita Federal está temporariamente fora do ar".
        "origem_indisponivel": origem_indisponivel,
    }


@router.post("/monitorar")
@limiter.limit("12/minute")
async def monitorar(request: Request, body: MonitorarIn, ctx: Contexto = Depends(contexto_atual)):
    """Adiciona um CNPJ à carteira monitorada, avalia e persiste o score."""
    if not settings.infosimples_token:
        raise HTTPException(status_code=400, detail="Consulta de regularidade (CND) temporariamente indisponível.")
    cnpjs = _normalizar_cnpjs([body.cnpj])
    if not cnpjs:
        raise HTTPException(status_code=422, detail="CNPJ inválido.")

    # Reserva atômica (não check-then-consume): só segue se houver saldo no momento da
    # reserva. Sob concorrência, restante>0 pode mentir entre o check e o consumir (TOCTOU).
    if not budget.consumir("cnd"):
        raise HTTPException(status_code=429, detail="Teto diário de consultas atingido.")
    if not budget.consumir("cnpj"):
        budget.devolver("cnd")  # estorna o que já reservei nesta operação
        raise HTTPException(status_code=429, detail="Teto diário de consultas atingido.")
    try:
        async with httpx.AsyncClient() as client:
            avaliacao = await service.avaliar_cnpj(cnpjs[0], client)
    except cnpj_lookup.RateLimitError:
        budget.devolver("cnpj")
        budget.devolver("cnd")
        raise HTTPException(
            status_code=429,
            detail="Limite de consultas por minuto atingido. Aguarde cerca de 1 minuto e tente de novo.",
        )
    except cnpj_lookup.LookupError:
        budget.devolver("cnpj")
        budget.devolver("cnd")
        raise HTTPException(status_code=502, detail="Consulta de CNPJ indisponível no momento.")

    async with async_session_factory() as session:
        f = await repo.upsert_monitorado(session, ctx.escritorio_id, avaliacao)
        if avaliacao["faixa"] == "ALTO":
            await repo.criar_alerta(
                session, ctx.escritorio_id, f.id, "SCORE_CRITICO",
                f"{avaliacao.get('razao_social') or avaliacao['cnpj']} entrou com score {avaliacao['score']} (risco alto).",
            )

    await _associar(ctx.escritorio_id, [avaliacao.get("cnpj")])
    cnd_concluida = 1 if avaliacao.get("status_cnd") and avaliacao["status_cnd"] != "FALHA" else 0
    await _registrar_consumo(
        ctx.escritorio_id, "modulo02", "avaliacao_individual", 1, cnd_concluida, contexto="monitorar"
    )
    return {**avaliacao, "monitorado": True}


@router.post("/reavaliar")
@limiter.limit("2/minute")
async def reavaliar(request: Request, ctx: Contexto = Depends(contexto_atual)):
    """Re-consulta a carteira monitorada agora (sob demanda), gerando alertas em mudança.

    Reavalia a carteira do PRÓPRIO escritório (inclusive admin: reavalia a dele).
    """
    if not settings.infosimples_token:
        raise HTTPException(status_code=400, detail="Consulta de regularidade (CND) temporariamente indisponível.")
    async with async_session_factory() as session:
        return await service.reavaliar_carteira(session, ctx.escritorio_id)


@router.get("/monitorados")
async def monitorados(ctx: Contexto = Depends(contexto_atual)):
    """Carteira monitorada, ordenada por score (pior primeiro). Admin vê de todos os escritórios."""
    try:
        async with async_session_factory() as session:
            forns = await repo.listar_monitorados(session, ctx.filtro_escritorio)
    except Exception:
        raise HTTPException(status_code=503, detail="Carteira temporariamente indisponível.")
    return [
        {
            "id": f.id,
            "cnpj": f.cnpj,
            "razao_social": f.razao_social,
            "score_atual": f.score_atual,
            "status_cnd_atual": f.status_cnd_atual,
            "ultima_consulta": f.ultima_consulta.isoformat() if f.ultima_consulta else None,
        }
        for f in forns
    ]


@router.get("/alertas")
async def alertas(ctx: Contexto = Depends(contexto_atual)):
    try:
        async with async_session_factory() as session:
            itens = await repo.listar_alertas(session, ctx.filtro_escritorio)
    except Exception:
        raise HTTPException(status_code=503, detail="Alertas temporariamente indisponíveis.")
    return [
        {
            "id": a.id,
            "tipo": a.tipo,
            "mensagem": a.mensagem,
            "lido": a.lido,
            "criado_em": a.criado_em.isoformat() if a.criado_em else None,
        }
        for a in itens
    ]
