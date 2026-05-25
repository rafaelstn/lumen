"""Acesso ao banco de fornecedores (cache persistente de CNPJ ↔ razão social).

Casamento por nome normalizado: análises futuras reusam CNPJ já resolvido, de graça,
sem reconsultar API paga. Toda operação é tolerante (o chamador trata indisponibilidade).
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fornecedor import Fornecedor, FornecedorAlias
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


async def _fornecedor_por_cnpj(session: AsyncSession, cnpj: str) -> Fornecedor | None:
    res = await session.execute(select(Fornecedor).where(Fornecedor.cnpj == cnpj).limit(1))
    return res.scalar_one_or_none()


async def casar(session: AsyncSession, nome_entrada: str) -> Fornecedor | None:
    """Resolve um nome de entrada para um Fornecedor, de graça (sem API).

    1. Procura PRIMEIRO no alias (grafia de entrada -> cnpj). É o caminho que evita
       reconsulta: o nome do arquivo casa mesmo divergindo do nome oficial salvo.
    2. Fallback: casa pela razão social normalizada do próprio Fornecedor.

    A razão social de exibição sempre vem do Fornecedor (pelo CNPJ).
    """
    norm = _normalizar(nome_entrada)
    if not norm:
        return None
    res = await session.execute(
        select(FornecedorAlias).where(FornecedorAlias.nome_normalizado == norm).limit(1)
    )
    alias = res.scalar_one_or_none()
    if alias:
        forn = await _fornecedor_por_cnpj(session, alias.cnpj)
        if forn:
            return forn
        # Alias sem Fornecedor correspondente (caso raro): ainda casa pelo CNPJ do alias.
        return Fornecedor(cnpj=alias.cnpj, razao_social=nome_entrada, nome_normalizado=norm)
    return await buscar_exato(session, nome_entrada)


async def registrar_alias(session: AsyncSession, nome_entrada: str, cnpj: str) -> None:
    """Upsert idempotente do alias (grafia de entrada normalizada -> cnpj).

    Tolerante: nome/cnpj vazio é no-op. Se a grafia já existe, atualiza o CNPJ
    (não duplica). É o que torna a re-análise gratuita para nomes já vistos.
    """
    if not nome_entrada or not cnpj:
        return
    norm = _normalizar(nome_entrada)
    if not norm:
        return
    res = await session.execute(
        select(FornecedorAlias).where(FornecedorAlias.nome_normalizado == norm)
    )
    existente = res.scalar_one_or_none()
    if existente:
        existente.cnpj = cnpj
    else:
        session.add(FornecedorAlias(nome_normalizado=norm, cnpj=cnpj))
    await session.commit()


async def buscar(session: AsyncSession, q: str, limite: int = 10) -> list[Fornecedor]:
    """Busca textual (campo de pesquisa manual gratuita)."""
    norm = _normalizar(q)
    if len(norm) < 3:
        return []
    res = await session.execute(
        select(Fornecedor).where(Fornecedor.nome_normalizado.ilike(f"%{norm}%")).limit(limite)
    )
    return list(res.scalars())


async def registrar_cnd(
    session: AsyncSession,
    cnpj: str,
    status: str,
    quando: datetime | None = None,
    razao_social: str | None = None,
) -> None:
    """Registra, por CNPJ, quando e qual foi a última consulta de CND concluída.

    Metadado de controle (não é fonte de verdade da regularidade). Idempotente por CNPJ.
    Tolerante: cnpj/status vazio é no-op. Não chamar com FALHA: o chamador só registra
    quando obteve um status real, para não mascarar o que é recente.

    Se o CNPJ ainda não existe no banco de fornecedores (ex.: CND consultada antes de o
    cadastro ter sido salvo), cria um registro mínimo. Não sobrescreve uma razão social
    boa já existente: só preenche a razão se vier uma e o registro ainda não tiver.
    """
    if not cnpj or not status:
        return
    quando = quando or datetime.now(timezone.utc)
    existente = await _fornecedor_por_cnpj(session, cnpj)
    if existente:
        existente.cnd_ultima_consulta = quando
        existente.cnd_ultimo_status = status
    else:
        nome = (razao_social or "").strip() or f"CNPJ {cnpj}"
        session.add(
            Fornecedor(
                cnpj=cnpj,
                razao_social=nome,
                nome_normalizado=_normalizar(nome),
                origem="cnd",
                cnd_ultima_consulta=quando,
                cnd_ultimo_status=status,
            )
        )
    await session.commit()


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
