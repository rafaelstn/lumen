"""Endpoints administrativos — /api/admin. Acesso restrito ao admin (role='admin').

Base mínima para o Rafael validar o papel admin. O dashboard completo de métricas vem
numa etapa seguinte. Protegido pela dependency somente_admin (403 se não for admin).
"""
from fastapi import APIRouter, Depends, HTTPException

from app.auth import service
from app.auth.deps import Contexto, somente_admin
from app.auth.schemas import EscritorioOut
from app.database import async_session_factory

router = APIRouter()


@router.get("/escritorios", response_model=list[EscritorioOut])
async def listar_escritorios(ctx: Contexto = Depends(somente_admin)):
    """Lista todos os escritórios (com contagem de usuários). Só admin."""
    try:
        async with async_session_factory() as session:
            itens = await service.listar_escritorios(session)
    except Exception:
        raise HTTPException(status_code=503, detail="Indisponível no momento.")
    return [EscritorioOut(**item) for item in itens]
