"""Endpoints de consumo de APIs pagas — histórico do audit trail.

Router fino: validação na borda (Pydantic) e orquestração. Lógica no módulo consumo.
Escopado por escritório (single-tenant no MVP via escritorio_atual).
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.deps import escritorio_atual
from app.database import async_session_factory
from app.modules.consumo import repo, service
from app.modules.consumo.schemas import HistoricoOut

router = APIRouter()


@router.get("/historico", response_model=HistoricoOut)
async def historico(
    inicio: str | None = Query(None, description="Data inicial (YYYY-MM-DD ou ISO 8601)."),
    fim: str | None = Query(None, description="Data final (YYYY-MM-DD ou ISO 8601)."),
    escritorio: str = Depends(escritorio_atual),
):
    """Lista de consultas pagas no período + totais e séries por dia/mês."""
    try:
        ini = service.parse_data(inicio)
        f = service.parse_data(fim)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    try:
        async with async_session_factory() as session:
            logs = await repo.listar_historico(session, escritorio, ini, f)
    except Exception:
        raise HTTPException(status_code=503, detail="Histórico temporariamente indisponível.")
    return HistoricoOut(**service.montar_historico(logs))
