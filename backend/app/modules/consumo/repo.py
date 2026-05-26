"""Persistência do consumo: registra ConsultaLog (audit trail) e lista o histórico.

Atomicidade: `registrar_consulta` aceita uma sessão externa para gravar o audit trail
DENTRO da mesma transação da operação de negócio (ex.: upsert do monitorado no M02).
Quando não há transação de negócio (M01, store em memória), abre sessão própria e commita.
"""
from datetime import datetime
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.modules.consumo import pricing
from app.modules.consumo.models import SERVICO_CND, SERVICO_CNPJ, ConsultaLog


def _novo_log(
    *,
    escritorio_id: str,
    modulo: str,
    servico: str,
    operacao: str,
    quantidade: int,
    creditos_consumidos: int,
    consumo_estimado: bool,
    contexto: str | None,
) -> ConsultaLog:
    """Monta o registro com o custo já calculado em centavos (snapshot do preço)."""
    preco = pricing.preco_unitario_centavos_snapshot(servico)
    custo = pricing.custo_centavos(servico, creditos_consumidos)
    return ConsultaLog(
        escritorio_id=escritorio_id,
        modulo=modulo,
        servico=servico,
        operacao=operacao,
        quantidade=quantidade,
        creditos_consumidos=creditos_consumidos,
        preco_unitario_centavos=preco,
        custo_centavos=custo,
        consumo_estimado=consumo_estimado,
        contexto=contexto,
    )


async def registrar_consulta(
    *,
    escritorio_id: str,
    modulo: str,
    servico: str,
    operacao: str,
    quantidade: int,
    creditos_consumidos: int,
    consumo_estimado: bool = True,
    contexto: str | None = None,
    session: AsyncSession | None = None,
) -> ConsultaLog:
    """Grava um registro no audit trail.

    Se `session` for passada, apenas adiciona+flush (o commit é do chamador, atômico
    com a operação de negócio). Sem session, abre uma própria e commita.
    """
    log = _novo_log(
        escritorio_id=escritorio_id,
        modulo=modulo,
        servico=servico,
        operacao=operacao,
        quantidade=quantidade,
        creditos_consumidos=creditos_consumidos,
        consumo_estimado=consumo_estimado,
        contexto=contexto,
    )
    if session is not None:
        session.add(log)
        await session.flush()  # garante id; commit fica com a transação do chamador
        return log

    async with async_session_factory() as own:
        own.add(log)
        await own.commit()
        return log


async def registrar_cnpj(
    *,
    escritorio_id: str,
    modulo: str,
    operacao: str,
    consultas: int,
    contexto: str | None = None,
    session: AsyncSession | None = None,
) -> ConsultaLog | None:
    """Atalho: registra `consultas` chamadas ao CNPJá (estimativa de 2 créditos por consulta).

    Não grava nada se consultas <= 0 (ex.: nada foi efetivamente consultado).
    """
    if consultas <= 0:
        return None
    return await registrar_consulta(
        escritorio_id=escritorio_id,
        modulo=modulo,
        servico=SERVICO_CNPJ,
        operacao=operacao,
        quantidade=consultas,
        creditos_consumidos=consultas * pricing.CREDITOS_POR_CONSULTA_CNPJ,
        consumo_estimado=True,
        contexto=contexto,
        session=session,
    )


async def registrar_cnd(
    *,
    escritorio_id: str,
    modulo: str,
    operacao: str,
    consultas_cobradas: int,
    contexto: str | None = None,
    session: AsyncSession | None = None,
) -> ConsultaLog | None:
    """Atalho: registra `consultas_cobradas` CNDs (1 crédito cada).

    Cobradas = requisições que a Infosimples FATUROU (header.billable), o que inclui falhas
    como 611/612 (certidão incompleta/sem dados na origem). Antes contávamos só as concluídas
    (status != FALHA), o que subestimava a fatura. Não grava nada se consultas_cobradas <= 0.
    """
    if consultas_cobradas <= 0:
        return None
    return await registrar_consulta(
        escritorio_id=escritorio_id,
        modulo=modulo,
        servico=SERVICO_CND,
        operacao=operacao,
        quantidade=consultas_cobradas,
        creditos_consumidos=consultas_cobradas * pricing.CREDITOS_POR_CONSULTA_CND,
        consumo_estimado=True,
        contexto=contexto,
        session=session,
    )


async def listar_historico(
    session: AsyncSession,
    escritorio_id: str,
    inicio: datetime | None,
    fim: datetime | None,
) -> Sequence[ConsultaLog]:
    q = select(ConsultaLog).where(ConsultaLog.escritorio_id == escritorio_id)
    if inicio is not None:
        q = q.where(ConsultaLog.criado_em >= inicio)
    if fim is not None:
        q = q.where(ConsultaLog.criado_em <= fim)
    res = await session.execute(q.order_by(ConsultaLog.criado_em.desc()).limit(1000))
    return list(res.scalars())
