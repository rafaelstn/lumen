"""Acesso ao histórico de análises (tabela analises).

Persiste e reabre o estado completo de uma análise do M01 sem re-subir a planilha. O id da
Analise é o próprio job_id, então salvar/atualizar é um upsert idempotente (nunca duplica).

Toda escrita aqui é chamada de forma tolerante pelo router/tasks (não derrubar a operação se o
banco falhar): o dado essencial vive no JobStore em memória; o histórico é uma conveniência.
"""
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analise import Analise


def _estado(job: dict) -> dict:
    """Extrai o estado completo (fornecedores + resumo + metadados) de um job para gravar."""
    return {
        "fornecedores": job.get("fornecedores", []),
        "resumo": job.get("resumo", {}),
        "metadados": job.get("metadados", {}),
    }


async def salvar(session: AsyncSession, analise_id: str, job: dict) -> None:
    """Upsert idempotente da análise por id (= job_id). Cria ou atualiza o estado e atualizado_em.

    Tolerante: id vazio é no-op. Desnormaliza cliente/cnpj/periodo/total dos metadados+resumo
    para a listagem não precisar abrir o JSON pesado.
    """
    if not analise_id:
        return
    meta = job.get("metadados") or {}
    resumo = job.get("resumo") or {}
    fornecedores = job.get("fornecedores") or []
    total = resumo.get("total_fornecedores")
    if total is None:
        total = len(fornecedores)

    escritorio_id = job.get("escritorio_id")
    if not escritorio_id:
        from app.config import settings

        escritorio_id = settings.escritorio_default_id

    existente = await session.get(Analise, analise_id)
    if existente is None:
        session.add(
            Analise(
                id=analise_id,
                escritorio_id=escritorio_id,
                cliente=meta.get("cliente"),
                cnpj_cliente=meta.get("cnpj_cliente"),
                periodo=meta.get("periodo"),
                total_fornecedores=total,
                dados=_estado(job),
            )
        )
    else:
        existente.cliente = meta.get("cliente")
        existente.cnpj_cliente = meta.get("cnpj_cliente")
        existente.periodo = meta.get("periodo")
        existente.total_fornecedores = total
        existente.dados = _estado(job)
        existente.atualizado_em = datetime.now(timezone.utc)
    await session.commit()


async def listar(session: AsyncSession, escritorio_id: str) -> list[Analise]:
    """Lista o histórico do escritório (sem o payload pesado é responsabilidade do serializer).

    Ordenado por mais recente (atualizado_em desc). Retorna os ORM; o router projeta só os
    campos leves (id, cliente, cnpj_cliente, periodo, total_fornecedores, criado_em, atualizado_em).
    """
    res = await session.execute(
        select(Analise)
        .where(Analise.escritorio_id == escritorio_id)
        .order_by(Analise.atualizado_em.desc(), Analise.criado_em.desc())
    )
    return list(res.scalars())


async def obter(session: AsyncSession, analise_id: str, escritorio_id: str) -> Analise | None:
    """Lê uma análise do histórico (com o estado completo) para reabrir. 404 fica a cargo do router.

    Filtra por escritorio_id para não vazar análise de outro tenant (multi-tenant futuro).
    """
    if not analise_id:
        return None
    res = await session.execute(
        select(Analise).where(
            Analise.id == analise_id, Analise.escritorio_id == escritorio_id
        )
    )
    return res.scalar_one_or_none()


async def apagar(session: AsyncSession, analise_id: str, escritorio_id: str) -> bool:
    """Remove a análise do histórico. Devolve True se removeu algo (para o router devolver 404)."""
    if not analise_id:
        return False
    res = await session.execute(
        delete(Analise).where(
            Analise.id == analise_id, Analise.escritorio_id == escritorio_id
        )
    )
    await session.commit()
    return res.rowcount > 0
