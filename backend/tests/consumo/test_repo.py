"""Testes de persistência do consumo (DB async, SQLite in-memory).

Cobre: audit trail gravado por operação, custo em centavos sem perda, atomicidade do
registro junto da transação do chamador e filtro de histórico por período.
"""
from sqlalchemy import func, select

from app.modules.consumo import repo
from app.modules.consumo.models import ConsultaLog

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


async def test_registrar_cnd_sem_cobranca_nao_grava(session):
    # cnd_lote com 0 cobradas (nenhuma requisição faturada): nada é gravado.
    log = await repo.registrar_cnd(
        escritorio_id=ESC, modulo="modulo01", operacao="cnd_lote", consultas_cobradas=0,
    )
    assert log is None


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
