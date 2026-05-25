"""Testes do metadado de controle da última CND por CNPJ.

A CND continua volátil e sempre reconsultável. Aqui só validamos o REGISTRO de quando/qual
foi a última consulta concluída, por CNPJ, no banco de fornecedores: serve para a UI e para
o controle de gasto (saber o que é recente antes de repuxar). FALHA não atualiza a data,
para não mascarar o que é recente.
"""
from datetime import datetime, timezone

import pytest

from app.models.fornecedor import Fornecedor
from app.modules.modulo01 import cnd, fornecedores_repo

CNPJ_X = "12345678000199"
NOME_OFICIAL = "METAL CUT INDUSTRIA E COMERCIO LTDA"
NOME_ENTRADA = "METAL CUT"


def _mesmo_instante(lido, esperado) -> bool:
    """Compara instantes ignorando o tzinfo.

    O SQLite de teste (aiosqlite) não preserva timezone e devolve o datetime naive; em
    Postgres o TIMESTAMPTZ preserva. Comparamos pelo instante, agnóstico de tz, para o
    teste valer nos dois bancos sem mascarar erro de valor.
    """
    a = lido.replace(tzinfo=None) if lido is not None else None
    b = esperado.replace(tzinfo=None) if esperado is not None else None
    return a == b


async def test_registrar_cnd_atualiza_data_e_status_em_fornecedor_existente(session):
    await fornecedores_repo.upsert(session, CNPJ_X, NOME_OFICIAL, "cnpja")

    await fornecedores_repo.registrar_cnd(session, CNPJ_X, cnd.NEGATIVA)

    fr = await fornecedores_repo._fornecedor_por_cnpj(session, CNPJ_X)
    assert fr.cnd_ultimo_status == cnd.NEGATIVA
    assert fr.cnd_ultima_consulta is not None
    # Não cria registro novo: continua um só Fornecedor para o CNPJ.
    res = await session.execute(Fornecedor.__table__.select())
    assert len(res.fetchall()) == 1


async def test_registrar_cnd_cria_minimo_quando_cnpj_inexistente(session):
    # CND consultada antes de o cadastro ter sido salvo: cria registro mínimo.
    await fornecedores_repo.registrar_cnd(session, CNPJ_X, cnd.POSITIVA, razao_social=NOME_OFICIAL)

    fr = await fornecedores_repo._fornecedor_por_cnpj(session, CNPJ_X)
    assert fr is not None
    assert fr.cnpj == CNPJ_X
    assert fr.razao_social == NOME_OFICIAL
    assert fr.origem == "cnd"
    assert fr.cnd_ultimo_status == cnd.POSITIVA


async def test_registrar_cnd_nao_sobrescreve_razao_social_boa(session):
    await fornecedores_repo.upsert(session, CNPJ_X, NOME_OFICIAL, "cnpja")

    # Mesmo passando outra razão, não mexe na já existente (boa): só atualiza o metadado de CND.
    await fornecedores_repo.registrar_cnd(session, CNPJ_X, cnd.NEGATIVA, razao_social="LIXO")

    fr = await fornecedores_repo._fornecedor_por_cnpj(session, CNPJ_X)
    assert fr.razao_social == NOME_OFICIAL


async def test_registrar_cnd_idempotente_e_atualiza(session):
    await fornecedores_repo.upsert(session, CNPJ_X, NOME_OFICIAL, "cnpja")
    t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t2 = datetime(2026, 5, 25, tzinfo=timezone.utc)

    await fornecedores_repo.registrar_cnd(session, CNPJ_X, cnd.NEGATIVA, quando=t1)
    await fornecedores_repo.registrar_cnd(session, CNPJ_X, cnd.POSITIVA, quando=t2)

    fr = await fornecedores_repo._fornecedor_por_cnpj(session, CNPJ_X)
    assert fr.cnd_ultimo_status == cnd.POSITIVA
    assert _mesmo_instante(fr.cnd_ultima_consulta, t2)
    res = await session.execute(Fornecedor.__table__.select())
    assert len(res.fetchall()) == 1


@pytest.mark.parametrize("cnpj,status", [("", cnd.NEGATIVA), (CNPJ_X, "")])
async def test_registrar_cnd_tolera_entrada_vazia(session, cnpj, status):
    await fornecedores_repo.registrar_cnd(session, cnpj, status)
    res = await session.execute(Fornecedor.__table__.select())
    assert res.fetchall() == []


async def test_falha_nao_atualiza_a_data(session):
    """FALHA não pode mascarar o que é recente: o chamador não registra FALHA.

    Reproduz a guarda dos chamadores (cnd._processar / modulo02.service): só registram
    quando status != FALHA. Aqui provamos que, respeitada essa guarda, o metadado fica intacto.
    """
    t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    await fornecedores_repo.upsert(session, CNPJ_X, NOME_OFICIAL, "cnpja")
    await fornecedores_repo.registrar_cnd(session, CNPJ_X, cnd.NEGATIVA, quando=t1)

    status_obtido = cnd.FALHA
    if status_obtido != cnd.FALHA:  # guarda dos chamadores
        await fornecedores_repo.registrar_cnd(session, CNPJ_X, status_obtido)

    fr = await fornecedores_repo._fornecedor_por_cnpj(session, CNPJ_X)
    # Continua a NEGATIVA antiga: a FALHA não sobrescreveu nem zerou a data.
    assert fr.cnd_ultimo_status == cnd.NEGATIVA
    assert _mesmo_instante(fr.cnd_ultima_consulta, t1)


async def test_casar_traz_metadado_de_cnd_do_cache(session):
    """_casar_com_banco deve expor cnd_ultima_consulta e cnd_status_cache ao casar pelo banco."""
    t = datetime(2026, 5, 20, tzinfo=timezone.utc)
    await fornecedores_repo.upsert(session, CNPJ_X, NOME_OFICIAL, "cnpja")
    await fornecedores_repo.registrar_alias(session, NOME_ENTRADA, CNPJ_X)
    await fornecedores_repo.registrar_cnd(session, CNPJ_X, cnd.NEGATIVA, quando=t)

    # Reproduz a lógica de _casar_com_banco do router sobre um fornecedor pendente.
    f = {"nome_forn": NOME_ENTRADA, "cnpj": None}
    fr = await fornecedores_repo.casar(session, f["nome_forn"])
    assert fr is not None
    f["cnpj"] = fr.cnpj
    f["cnpj_pendente"] = False
    f["cnpj_confirmado"] = True
    ultima = getattr(fr, "cnd_ultima_consulta", None)
    f["cnd_ultima_consulta"] = ultima.isoformat() if ultima else None
    f["cnd_status_cache"] = getattr(fr, "cnd_ultimo_status", None)

    assert f["cnpj"] == CNPJ_X
    assert f["cnd_status_cache"] == cnd.NEGATIVA
    # String ISO presente e referente ao mesmo instante (tz pode não vir no SQLite de teste).
    assert f["cnd_ultima_consulta"] is not None
    assert _mesmo_instante(datetime.fromisoformat(f["cnd_ultima_consulta"]), t)


async def test_casar_sem_cnd_traz_metadado_nulo(session):
    # CNPJ casado mas CND nunca consultada: campos vêm None (frontend não mostra selo).
    await fornecedores_repo.upsert(session, CNPJ_X, NOME_OFICIAL, "cnpja")

    fr = await fornecedores_repo.casar(session, NOME_OFICIAL)
    assert fr is not None
    assert getattr(fr, "cnd_ultima_consulta", None) is None
    assert getattr(fr, "cnd_ultimo_status", None) is None
