"""Acesso ao banco de fornecedores (cache persistente de CNPJ ↔ razão social).

Casamento por nome normalizado: análises futuras reusam CNPJ já resolvido, de graça,
sem reconsultar API paga. Toda operação é tolerante (o chamador trata indisponibilidade).
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fornecedor import Fornecedor
from app.modules.modulo01.cnpj_lookup import _normalizar


async def buscar_exato(session: AsyncSession, nome: str) -> Fornecedor | None:
    """Casa pela razão social normalizada (uso automático no processamento)."""
    norm = _normalizar(nome)
    if not norm:
        return None
    res = await session.execute(
        select(Fornecedor).where(Fornecedor.nome_normalizado == norm).limit(1)
    )
    return res.scalar_one_or_none()


async def buscar(session: AsyncSession, q: str, limite: int = 10) -> list[Fornecedor]:
    """Busca textual (campo de pesquisa manual gratuita)."""
    norm = _normalizar(q)
    if len(norm) < 3:
        return []
    res = await session.execute(
        select(Fornecedor).where(Fornecedor.nome_normalizado.ilike(f"%{norm}%")).limit(limite)
    )
    return list(res.scalars())


async def upsert(session: AsyncSession, cnpj: str, razao_social: str, origem: str = "manual") -> None:
    """Salva/atualiza o fornecedor no cache (idempotente por CNPJ)."""
    if not cnpj or not razao_social:
        return
    res = await session.execute(select(Fornecedor).where(Fornecedor.cnpj == cnpj))
    existente = res.scalar_one_or_none()
    if existente:
        existente.razao_social = razao_social
        existente.nome_normalizado = _normalizar(razao_social)
        existente.origem = origem
    else:
        session.add(
            Fornecedor(
                cnpj=cnpj,
                razao_social=razao_social,
                nome_normalizado=_normalizar(razao_social),
                origem=origem,
            )
        )
    await session.commit()
