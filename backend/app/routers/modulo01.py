"""Endpoints do Módulo 01 — Análise de Crédito ICMS e Regularidade Fiscal.

Regra de organização: routers não contêm lógica de negócio, apenas validação
de entrada e orquestração de chamadas para os módulos em app/modules/modulo01/.
Os endpoints de processamento, progresso e relatório são implementados nas
fases 2 a 5.
"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/status")
async def status():
    """Health check específico do Módulo 01."""
    return {"modulo": "01", "nome": "Análise de Crédito Fiscal", "status": "ok"}
