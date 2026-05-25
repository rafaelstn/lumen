"""Persistência do consumo: registra ConsultaLog, gerencia recarga e deriva saldo/histórico.

Atomicidade: `registrar_consulta` aceita uma sessão externa para gravar o audit trail
DENTRO da mesma transação da operação de negócio (ex.: upsert do monitorado no M02).
Quando não há transação de negócio (M01, store em memória), abre sessão própria e commita.

Saldo restante = creditos_comprados (recargas) - soma(creditos_consumidos no ConsultaLog).
Nunca consulta o provider ao vivo (decisão de produto: controle interno).
"""
from datetime import datetime
from decimal import Decimal
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.modules.consumo import pricing
from app.modules.consumo.models import SERVICO_CND, SERVICO_CNPJ, ConsultaLog, SaldoConta


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
    consultas_concluidas: int,
    contexto: str | None = None,
    session: AsyncSession | None = None,
) -> ConsultaLog | None:
    """Atalho: registra `consultas_concluidas` CNDs (1 crédito cada). FALHA não conta (0 crédito).

    Não grava nada se consultas_concluidas <= 0.
    """
    if consultas_concluidas <= 0:
        return None
    return await registrar_consulta(
        escritorio_id=escritorio_id,
        modulo=modulo,
        servico=SERVICO_CND,
        operacao=operacao,
        quantidade=consultas_concluidas,
        creditos_consumidos=consultas_concluidas * pricing.CREDITOS_POR_CONSULTA_CND,
        consumo_estimado=True,
        contexto=contexto,
        session=session,
    )


async def _consumido_por_servico(session: AsyncSession, escritorio_id: str, servico: str) -> int:
    res = await session.execute(
        select(func.coalesce(func.sum(ConsultaLog.creditos_consumidos), 0)).where(
            ConsultaLog.escritorio_id == escritorio_id, ConsultaLog.servico == servico
        )
    )
    return int(res.scalar_one())


def _insert_para_dialect(session: AsyncSession):
    """Escolhe o construtor INSERT com suporte a ON CONFLICT conforme o dialect da sessão.

    Postgres em produção, SQLite (aiosqlite) nos testes. Ambos suportam UPSERT; a API
    on_conflict_do_update difere só no módulo de origem.
    """
    name = session.bind.dialect.name
    if name == "postgresql":
        return pg_insert
    if name == "sqlite":
        return sqlite_insert
    raise RuntimeError(f"Dialect sem suporte a UPSERT no consumo: {name!r}.")


async def aplicar_recarga(
    session: AsyncSession,
    escritorio_id: str,
    servico: str,
    creditos: int,
    valor_total_centavos: int,
) -> SaldoConta:
    """Adiciona um PACOTE comprado ao saldo do serviço (acumula creditos e valor pago).

    UPSERT atômico incremental no banco (ON CONFLICT DO UPDATE somando no próprio SQL), sem
    read-modify-write em Python: elimina o lost update sob recargas concorrentes do mesmo
    (escritorio, servico). Preço por crédito é DERIVADO (valor_total / creditos), não gravado.
    """
    insert = _insert_para_dialect(session)
    stmt = insert(SaldoConta).values(
        escritorio_id=escritorio_id,
        servico=servico,
        creditos_comprados=creditos,
        valor_total_pago_centavos=valor_total_centavos,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["escritorio_id", "servico"],
        set_={
            "creditos_comprados": SaldoConta.creditos_comprados + stmt.excluded.creditos_comprados,
            "valor_total_pago_centavos": (
                SaldoConta.valor_total_pago_centavos + stmt.excluded.valor_total_pago_centavos
            ),
            "atualizado_em": func.now(),
        },
    )
    await session.execute(stmt)
    await session.commit()
    # Recarrega o estado consolidado pós-commit (expira o que estiver em cache da sessão).
    conta = await session.get(SaldoConta, (escritorio_id, servico))
    await session.refresh(conta)
    return conta


async def saldo_servico(session: AsyncSession, escritorio_id: str, servico: str) -> dict:
    """Saldo de um serviço: comprado, consumido (do log), restante e custo do restante.

    Preço por crédito é DERIVADO (valor_total_pago / creditos_comprados) em Decimal; cai no
    preço de referência enquanto não há recarga. O custo do restante usa esse Decimal e só
    arredonda no fim (ROUND_HALF_UP), nunca negativo.
    """
    conta = await session.get(SaldoConta, (escritorio_id, servico))
    comprados = conta.creditos_comprados if conta else 0
    valor_pago = conta.valor_total_pago_centavos if conta else 0
    consumidos = await _consumido_por_servico(session, escritorio_id, servico)
    restantes = comprados - consumidos
    preco_decimal = pricing.preco_por_credito_derivado(comprados, valor_pago, servico)
    return {
        "servico": servico,
        "creditos_comprados": comprados,
        "creditos_consumidos": consumidos,
        "creditos_restantes": restantes,
        "valor_total_pago_centavos": valor_pago,
        # Preço por crédito como string decimal (preserva a fração, ex.: "2.499").
        "preco_por_credito": _decimal_str(preco_decimal),
        # Custo do que ainda resta (referência de quanto saldo em R$ ainda há). Nunca negativo.
        "custo_restante_centavos": pricing.custo_centavos_por_preco(
            max(0, restantes), preco_decimal
        ),
    }


def _decimal_str(valor: Decimal) -> str:
    """Serializa o Decimal sem notação científica e sem zeros à esquerda artificiais."""
    return format(valor.normalize(), "f")


def preco_por_credito_str(conta: SaldoConta) -> str:
    """Preço por crédito derivado da conta, como string decimal (centavos, fração preservada)."""
    preco = pricing.preco_por_credito_derivado(
        conta.creditos_comprados, conta.valor_total_pago_centavos, conta.servico
    )
    return _decimal_str(preco)


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
