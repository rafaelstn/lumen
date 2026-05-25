"""Endpoints do Módulo 02 — Score Fiscal e monitoramento de fornecedores.

Consultas pagas (CNPJá + Infosimples) protegidas por teto de orçamento + clamp.
Tenant pelo escritório atual (single-tenant no MVP via escritorio_atual).
"""
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth.deps import escritorio_atual
from app.config import settings
from app.database import async_session_factory
from app.modules.consumo import repo as consumo_repo
from app.modules.modulo01 import budget, cnpj_lookup
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


def _orcamento_ok() -> bool:
    return budget.restante("cnd") > 0 and budget.restante("cnpj") > 0


async def _registrar_consumo(
    escritorio: str, modulo: str, operacao: str,
    consultas_cnpj: int, cnds_concluidas: int, contexto: str | None,
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
            consultas_concluidas=cnds_concluidas, contexto=contexto,
        )
    except Exception:
        import logging
        logging.getLogger("modulo02").warning(
            "Falha ao registrar audit trail de consumo (op=%s).", operacao, exc_info=True
        )


@router.post("/due-diligence")
@limiter.limit("4/minute")
async def due_diligence(
    request: Request, body: DueDiligenceIn, escritorio: str = Depends(escritorio_atual)
):
    """Avalia uma lista de CNPJs (score 0-100) e devolve o ranking (pior primeiro)."""
    if not settings.infosimples_token:
        raise HTTPException(status_code=400, detail="Consulta de regularidade (CND) temporariamente indisponível.")

    cnpjs = _normalizar_cnpjs(body.cnpjs)[: settings.cnd_limite_max]
    if not cnpjs:
        raise HTTPException(status_code=422, detail="Nenhum CNPJ válido na lista.")

    resultados = []
    teto_atingido = False
    consultas_cnpj = 0       # nº de consultas ao CNPJá (2 créditos cada, estimado)
    cnds_concluidas = 0      # nº de CNDs concluídas (1 crédito cada; FALHA não conta)
    async with httpx.AsyncClient() as client:
        for c in cnpjs:
            if not _orcamento_ok():
                teto_atingido = True
                break
            budget.consumir("cnd")
            budget.consumir("cnpj")
            r = await service.avaliar_cnpj(c, client)
            consultas_cnpj += 1
            if r.get("status_cnd") and r["status_cnd"] != "FALHA":
                cnds_concluidas += 1
            resultados.append(r)

    await _registrar_consumo(
        escritorio, "modulo02", "due_diligence", consultas_cnpj, cnds_concluidas,
        contexto=f"{len(resultados)} cnpj(s)",
    )
    resultados.sort(key=lambda r: r["score"])  # pior score primeiro (maior risco)
    return {"resultados": resultados, "avaliados": len(resultados), "teto_atingido": teto_atingido}


@router.post("/monitorar")
@limiter.limit("12/minute")
async def monitorar(request: Request, body: MonitorarIn, escritorio: str = Depends(escritorio_atual)):
    """Adiciona um CNPJ à carteira monitorada, avalia e persiste o score."""
    if not settings.infosimples_token:
        raise HTTPException(status_code=400, detail="Consulta de regularidade (CND) temporariamente indisponível.")
    cnpjs = _normalizar_cnpjs([body.cnpj])
    if not cnpjs:
        raise HTTPException(status_code=422, detail="CNPJ inválido.")
    if not _orcamento_ok():
        raise HTTPException(status_code=429, detail="Teto diário de consultas atingido.")

    budget.consumir("cnd")
    budget.consumir("cnpj")
    async with httpx.AsyncClient() as client:
        avaliacao = await service.avaliar_cnpj(cnpjs[0], client)

    async with async_session_factory() as session:
        f = await repo.upsert_monitorado(session, escritorio, avaliacao)
        if avaliacao["faixa"] == "ALTO":
            await repo.criar_alerta(
                session, escritorio, f.id, "SCORE_CRITICO",
                f"{avaliacao.get('razao_social') or avaliacao['cnpj']} entrou com score {avaliacao['score']} (risco alto).",
            )

    cnd_concluida = 1 if avaliacao.get("status_cnd") and avaliacao["status_cnd"] != "FALHA" else 0
    await _registrar_consumo(
        escritorio, "modulo02", "avaliacao_individual", 1, cnd_concluida, contexto="monitorar"
    )
    return {**avaliacao, "monitorado": True}


@router.post("/reavaliar")
@limiter.limit("2/minute")
async def reavaliar(request: Request, escritorio: str = Depends(escritorio_atual)):
    """Re-consulta a carteira monitorada agora (sob demanda), gerando alertas em mudança."""
    if not settings.infosimples_token:
        raise HTTPException(status_code=400, detail="Consulta de regularidade (CND) temporariamente indisponível.")
    async with async_session_factory() as session:
        return await service.reavaliar_carteira(session, escritorio)


@router.get("/monitorados")
async def monitorados(escritorio: str = Depends(escritorio_atual)):
    """Carteira monitorada, ordenada por score (pior primeiro)."""
    try:
        async with async_session_factory() as session:
            forns = await repo.listar_monitorados(session, escritorio)
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
async def alertas(escritorio: str = Depends(escritorio_atual)):
    try:
        async with async_session_factory() as session:
            itens = await repo.listar_alertas(session, escritorio)
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
