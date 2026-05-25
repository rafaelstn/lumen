"""Persistência do Módulo 02 (fornecedores monitorados, histórico de CND, alertas).

Todas as operações são escopadas por escritorio_id (multi-tenant desde o schema).
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.modulo02.models import Alerta, FornecedorMonitorado, HistoricoCnd


async def listar_monitorados(
    session: AsyncSession, escritorio_id: str | None
) -> list[FornecedorMonitorado]:
    """Carteira do escritório. `escritorio_id`=None (admin) lista de todos os escritórios."""
    stmt = select(FornecedorMonitorado).where(FornecedorMonitorado.ativo)
    if escritorio_id is not None:
        stmt = stmt.where(FornecedorMonitorado.escritorio_id == escritorio_id)
    res = await session.execute(
        stmt.order_by(FornecedorMonitorado.score_atual.asc().nulls_last())
    )
    return list(res.scalars())


async def obter_por_cnpj(session, escritorio_id: str, cnpj: str) -> FornecedorMonitorado | None:
    res = await session.execute(
        select(FornecedorMonitorado).where(
            FornecedorMonitorado.escritorio_id == escritorio_id, FornecedorMonitorado.cnpj == cnpj
        )
    )
    return res.scalar_one_or_none()


async def upsert_monitorado(session, escritorio_id: str, avaliacao: dict) -> FornecedorMonitorado:
    """Cria/atualiza o fornecedor monitorado com a última avaliação e grava o histórico."""
    f = await obter_por_cnpj(session, escritorio_id, avaliacao["cnpj"])
    if f is None:
        f = FornecedorMonitorado(escritorio_id=escritorio_id, cnpj=avaliacao["cnpj"])
        session.add(f)
    f.razao_social = avaliacao.get("razao_social")
    f.ativo = True
    f.score_atual = avaliacao["score"]
    f.status_cnd_atual = avaliacao["status_cnd"]
    f.ultima_consulta = datetime.now(timezone.utc)
    await session.flush()  # garante f.id

    session.add(
        HistoricoCnd(
            fornecedor_id=f.id,
            escritorio_id=escritorio_id,
            status=avaliacao["status_cnd"],
            score=avaliacao["score"],
            detalhes={"faixa": avaliacao["faixa"], "componentes": avaliacao["componentes"]},
        )
    )
    await session.commit()
    return f


async def criar_alerta(session, escritorio_id: str, fornecedor_id: str, tipo: str, mensagem: str) -> None:
    session.add(
        Alerta(escritorio_id=escritorio_id, fornecedor_id=fornecedor_id, tipo=tipo, mensagem=mensagem)
    )
    await session.commit()


async def listar_alertas(session, escritorio_id: str | None, apenas_nao_lidos: bool = False) -> list[Alerta]:
    """Alertas do escritório. `escritorio_id`=None (admin) lista de todos os escritórios."""
    q = select(Alerta)
    if escritorio_id is not None:
        q = q.where(Alerta.escritorio_id == escritorio_id)
    if apenas_nao_lidos:
        q = q.where(~Alerta.lido)
    res = await session.execute(q.order_by(Alerta.criado_em.desc()).limit(100))
    return list(res.scalars())
