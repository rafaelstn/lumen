"""Endpoints de consumo de APIs pagas — saldo (controle interno), recarga e histórico.

Router fino: validação na borda (Pydantic) e orquestração. Lógica no módulo consumo.
Escopado por escritório (single-tenant no MVP via escritorio_atual).
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.auth.deps import escritorio_atual
from app.database import async_session_factory
from app.modules.consumo import repo, service
from app.modules.consumo.models import SERVICOS_VALIDOS
from app.modules.consumo.schemas import (
    HistoricoOut,
    RecargaIn,
    RecargaOut,
    SaldoOut,
)
from app.ratelimit import limiter

router = APIRouter()


@router.get("/saldo", response_model=SaldoOut)
async def saldo(escritorio: str = Depends(escritorio_atual)):
    """Saldo por serviço: comprado, consumido (do audit trail), restante e custo do restante."""
    try:
        async with async_session_factory() as session:
            itens = [
                await repo.saldo_servico(session, escritorio, servico)
                for servico in SERVICOS_VALIDOS
            ]
    except Exception:
        raise HTTPException(status_code=503, detail="Saldo temporariamente indisponível.")
    return SaldoOut(itens=itens)


@router.post("/recarga", response_model=RecargaOut)
@limiter.limit("30/minute")
async def recarga(request: Request, body: RecargaIn, escritorio: str = Depends(escritorio_atual)):
    """Registra uma recarga (créditos comprados) para um serviço. Acumula no saldo."""
    try:
        async with async_session_factory() as session:
            conta = await repo.aplicar_recarga(
                session, escritorio, body.servico, body.creditos, body.valor_total_centavos
            )
            preco = repo.preco_por_credito_str(conta)
    except Exception:
        raise HTTPException(status_code=503, detail="Não foi possível registrar a recarga.")
    return RecargaOut(
        servico=conta.servico,
        creditos_comprados=conta.creditos_comprados,
        valor_total_pago_centavos=conta.valor_total_pago_centavos,
        preco_por_credito=preco,
        atualizado_em=conta.atualizado_em,
    )


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
