"""Testes de persistência do consumo (DB async, SQLite in-memory).

Cobre: audit trail gravado por operação, saldo restante = comprado - consumido,
custo em centavos sem perda, atomicidade do registro junto da transação do chamador.
"""
import asyncio

from sqlalchemy import func, select

from app.modules.consumo import repo
from app.modules.consumo.models import ConsultaLog, SaldoConta

ESC = "00000000-0000-0000-0000-000000000001"


async def test_registrar_consulta_grava_audit_trail_com_custo(session):
    log = await repo.registrar_consulta(
        escritorio_id=ESC, modulo="modulo02", servico="cnd", operacao="due_diligence",
        quantidade=3, creditos_consumidos=3, contexto="3 cnpj(s)", session=session,
    )
    await session.commit()
    assert log.id is not None
    assert log.creditos_consumidos == 3
    assert log.preco_unitario_centavos == 26
    assert log.custo_centavos == 78  # 3 * 26
    assert log.consumo_estimado is True

    total = await session.scalar(select(func.count()).select_from(ConsultaLog))
    assert total == 1


async def test_registrar_cnpj_estima_dois_creditos_por_consulta(session):
    log = await repo.registrar_cnpj(
        escritorio_id=ESC, modulo="modulo01", operacao="enriquecimento", consultas=5,
        session=session,
    )
    await session.commit()
    assert log.quantidade == 5
    assert log.creditos_consumidos == 10  # 5 consultas * 2 créditos
    assert log.custo_centavos == 25       # 10 créditos * 2,499 -> ROUND_HALF_UP = 25 centavos


async def test_registrar_cnpj_zero_consultas_nao_grava(session):
    log = await repo.registrar_cnpj(
        escritorio_id=ESC, modulo="modulo01", operacao="enriquecimento", consultas=0,
    )
    assert log is None
    total = await session.scalar(select(func.count()).select_from(ConsultaLog))
    assert total == 0


async def test_registrar_cnd_falha_nao_consome(session):
    # cnd_lote com 0 concluídas (todas FALHA): nada é gravado.
    log = await repo.registrar_cnd(
        escritorio_id=ESC, modulo="modulo01", operacao="cnd_lote", consultas_concluidas=0,
    )
    assert log is None


async def test_recarga_acumula_creditos_e_valor_pago(session):
    # Pacote CNPJá: 1000 créditos por R$24,99 (2499 centavos).
    c1 = await repo.aplicar_recarga(session, ESC, "cnpj", 1000, 2499)
    assert c1.creditos_comprados == 1000
    assert c1.valor_total_pago_centavos == 2499
    # Segundo pacote: 500 créditos por R$12,50 (1250 centavos). Acumula créditos e valor.
    c2 = await repo.aplicar_recarga(session, ESC, "cnpj", 500, 1250)
    assert c2.creditos_comprados == 1500
    assert c2.valor_total_pago_centavos == 3749
    # Preço por crédito DERIVADO = 3749 / 1500 = 2,499333... (fração mantida em Decimal).
    assert repo.preco_por_credito_str(c2).startswith("2.499")

    total = await session.scalar(select(func.count()).select_from(SaldoConta))
    assert total == 1  # mesma conta (escritorio, servico)


async def test_recargas_concorrentes_sem_lost_update(session_factory):
    # N recargas concorrentes do mesmo (escritorio, servico): a soma final tem que bater
    # exatamente com a soma de todas (prova que o UPSERT atômico elimina o lost update).
    n = 20
    creditos_por_recarga = 100
    valor_por_recarga = 250

    async def _recarga():
        async with session_factory() as s:
            await repo.aplicar_recarga(s, ESC, "cnpj", creditos_por_recarga, valor_por_recarga)

    await asyncio.gather(*[_recarga() for _ in range(n)])

    async with session_factory() as s:
        saldo = await repo.saldo_servico(s, ESC, "cnpj")
    assert saldo["creditos_comprados"] == n * creditos_por_recarga          # 2000
    assert saldo["valor_total_pago_centavos"] == n * valor_por_recarga      # 5000


async def test_saldo_restante_e_comprado_menos_consumido(session):
    # Pacote CND: 100 créditos por R$26,00 (2600 centavos) -> 26 centavos/crédito derivado.
    await repo.aplicar_recarga(session, ESC, "cnd", 100, 2600)
    await repo.registrar_cnd(
        escritorio_id=ESC, modulo="modulo02", operacao="due_diligence", consultas_concluidas=10,
        session=session,
    )
    await session.commit()
    saldo = await repo.saldo_servico(session, ESC, "cnd")
    assert saldo["creditos_comprados"] == 100
    assert saldo["creditos_consumidos"] == 10
    assert saldo["creditos_restantes"] == 90
    assert saldo["valor_total_pago_centavos"] == 2600
    assert saldo["preco_por_credito"] == "26"
    assert saldo["custo_restante_centavos"] == 90 * 26  # 2340


async def test_saldo_sem_recarga_nem_consumo(session):
    saldo = await repo.saldo_servico(session, ESC, "cnpj")
    assert saldo["creditos_comprados"] == 0
    assert saldo["creditos_consumidos"] == 0
    assert saldo["creditos_restantes"] == 0
    assert saldo["custo_restante_centavos"] == 0


async def test_saldo_pode_ficar_negativo_mas_custo_restante_nao(session):
    # Consumiu mais do que comprou (controle interno desatualizado): restante negativo,
    # mas custo do restante nunca negativo.
    await repo.aplicar_recarga(session, ESC, "cnpj", 2, 5)  # 2 créditos por 5 centavos
    await repo.registrar_cnpj(
        escritorio_id=ESC, modulo="modulo01", operacao="enriquecimento", consultas=5, session=session
    )
    await session.commit()
    saldo = await repo.saldo_servico(session, ESC, "cnpj")
    assert saldo["creditos_restantes"] == 2 - 10  # -8
    assert saldo["custo_restante_centavos"] == 0


async def test_atomicidade_log_na_transacao_do_chamador(session):
    # Passa a session do chamador: o log é flushed mas só persiste no commit do chamador.
    await repo.registrar_consulta(
        escritorio_id=ESC, modulo="modulo02", servico="cnd", operacao="avaliacao_individual",
        quantidade=1, creditos_consumidos=1, session=session,
    )
    # Antes do commit, ainda visível na própria session (flush).
    visivel = await session.scalar(select(func.count()).select_from(ConsultaLog))
    assert visivel == 1
    # Rollback do chamador desfaz o log (atomicidade real com a operação de negócio).
    await session.rollback()
    apos_rollback = await session.scalar(select(func.count()).select_from(ConsultaLog))
    assert apos_rollback == 0


async def test_historico_filtra_por_periodo(session):
    from datetime import datetime, timezone

    # Insere logs com datas distintas manualmente (server_default não controlável aqui).
    for dia, cred in [(20, 1), (24, 2), (25, 3)]:
        session.add(
            ConsultaLog(
                escritorio_id=ESC, criado_em=datetime(2026, 5, dia, tzinfo=timezone.utc),
                modulo="modulo02", servico="cnd", operacao="due_diligence",
                quantidade=cred, creditos_consumidos=cred, preco_unitario_centavos=26,
                custo_centavos=cred * 26, consumo_estimado=True,
            )
        )
    await session.commit()

    todos = await repo.listar_historico(session, ESC, None, None)
    assert len(todos) == 3
    # Filtro [24, fim): exclui o dia 20.
    parcial = await repo.listar_historico(
        session, ESC, datetime(2026, 5, 24, tzinfo=timezone.utc), None
    )
    assert len(parcial) == 2
