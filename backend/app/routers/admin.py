"""Endpoints administrativos — /api/admin. Acesso restrito ao admin (role='admin').

Dashboard de administração do sistema (visão sistêmica do Rafael): quantos cadastros
existem, quanto cada escritório consome de crédito e uma visão geral. TODOS os endpoints
passam por `somente_admin` (403 se não for admin). Com auth_enabled=False o contexto é
anônimo não-admin, então o dashboard fica naturalmente fechado, que é o correto.

Router fino: validação de data na borda, agregação no admin_repo. Dinheiro em centavos
inteiros. Nenhum dado pessoal (sócios) é exposto; senha_hash nunca sai.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.deps import Contexto, somente_admin
from app.auth.schemas import (
    ConsumoEscritorioOut,
    EscritorioDetalheOut,
    EscritorioMetricasOut,
    ResumoAdminOut,
)
from app.database import async_session_factory
from app.modules.consumo import admin_repo
from app.modules.consumo import service as consumo_service

router = APIRouter()


def _parse_datas(inicio: str | None, fim: str | None) -> tuple[datetime | None, datetime | None]:
    """Valida inicio/fim (YYYY-MM-DD ou ISO). 422 se inválido."""
    try:
        return consumo_service.parse_data(inicio), consumo_service.parse_data(fim)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


def _inicio_mes_corrente() -> datetime:
    """Primeiro instante do mês corrente (UTC), para o recorte 'período corrente'."""
    agora = datetime.now(timezone.utc)
    return agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


@router.get("/resumo", response_model=ResumoAdminOut)
async def resumo(ctx: Contexto = Depends(somente_admin)):
    """Métricas gerais do sistema + consumo do mês corrente. Só admin."""
    inicio_mes = _inicio_mes_corrente()
    try:
        async with async_session_factory() as session:
            dados = await admin_repo.resumo_geral(session, inicio_mes, None)
    except Exception:
        raise HTTPException(status_code=503, detail="Indisponível no momento.")

    dados["consumo_periodo"] = {
        "inicio": inicio_mes.isoformat(),
        "fim": None,
        **dados["consumo_periodo"],
    }
    return ResumoAdminOut(**dados)


@router.get("/escritorios", response_model=list[EscritorioMetricasOut])
async def listar_escritorios(ctx: Contexto = Depends(somente_admin)):
    """Lista escritórios com agregações (usuários, análises, fornecedores, consumo, atividade).

    Ordenado por consumo desc; desempate pela atividade mais recente. Só admin.
    """
    try:
        async with async_session_factory() as session:
            itens = await admin_repo.escritorios_com_metricas(session)
    except Exception:
        raise HTTPException(status_code=503, detail="Indisponível no momento.")
    return [EscritorioMetricasOut(**item) for item in itens]


@router.get("/consumo-por-escritorio", response_model=list[ConsumoEscritorioOut])
async def consumo_por_escritorio(
    inicio: str | None = Query(None, description="Data inicial (YYYY-MM-DD ou ISO 8601)."),
    fim: str | None = Query(None, description="Data final (YYYY-MM-DD ou ISO 8601)."),
    ctx: Contexto = Depends(somente_admin),
):
    """Série de consumo de crédito agregada por escritório no período, com quebra por serviço."""
    ini, f = _parse_datas(inicio, fim)
    try:
        async with async_session_factory() as session:
            itens = await admin_repo.consumo_por_escritorio(session, ini, f)
    except Exception:
        raise HTTPException(status_code=503, detail="Indisponível no momento.")
    return [ConsumoEscritorioOut(**item) for item in itens]


@router.get("/escritorio/{escritorio_id}", response_model=EscritorioDetalheOut)
async def detalhe_escritorio(escritorio_id: str, ctx: Contexto = Depends(somente_admin)):
    """Detalhe de um escritório: usuários (sem senha), análises, consumo e quebra por serviço."""
    try:
        async with async_session_factory() as session:
            dados = await admin_repo.detalhe_escritorio(session, escritorio_id)
    except Exception:
        raise HTTPException(status_code=503, detail="Indisponível no momento.")
    if dados is None:
        raise HTTPException(status_code=404, detail="Escritório não encontrado.")
    return EscritorioDetalheOut(**dados)
