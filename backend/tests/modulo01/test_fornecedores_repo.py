"""Testes do alias de fornecedor: re-análise casa de graça, sem reconsultar a API paga.

Cenário central: o nome do arquivo (ex. "METAL CUT") difere do nome oficial salvo no
Fornecedor (ex. "METAL CUT INDUSTRIA E COMERCIO LTDA"). Sem o alias, a re-análise não
casaria pela razão social e o sistema repuxaria a API. Com o alias, casa pelo nome de
entrada, de graça.
"""
import pytest

from app.models.fornecedor import FornecedorAlias
from app.modules.modulo01 import cnpj_lookup, fornecedores_repo

CNPJ_X = "12345678000199"
NOME_ENTRADA = "METAL CUT"
NOME_OFICIAL = "METAL CUT INDUSTRIA E COMERCIO LTDA"


async def _semear_resolvido(session):
    """Simula o resultado de um enriquecimento: Fornecedor (nome oficial) + alias (nome de entrada)."""
    await fornecedores_repo.upsert(session, CNPJ_X, NOME_OFICIAL, "cnpja")
    await fornecedores_repo.registrar_alias(session, NOME_ENTRADA, CNPJ_X)


async def test_alias_resolve_nome_de_entrada_sem_api(session, monkeypatch):
    # Guard: qualquer toque na API derruba o teste. Provamos que o casamento é 100% local.
    async def _proibido(*args, **kwargs):
        raise AssertionError("A API de CNPJ NÃO pode ser chamada na re-análise.")

    monkeypatch.setattr(cnpj_lookup, "buscar_por_nome", _proibido)

    await _semear_resolvido(session)

    # Re-análise: o Livro de Entradas traz a grafia do arquivo ("METAL CUT").
    forn = await fornecedores_repo.casar(session, NOME_ENTRADA)
    assert forn is not None
    assert forn.cnpj == CNPJ_X
    # Exibição vem do Fornecedor (nome oficial), não do alias.
    assert forn.razao_social == NOME_OFICIAL


async def test_casamento_simula_casar_com_banco_sem_api(session, monkeypatch):
    # Reproduz a lógica de _casar_com_banco do router sobre a lista de fornecedores do job.
    async def _proibido(*args, **kwargs):
        raise AssertionError("A API de CNPJ NÃO pode ser chamada na re-análise.")

    monkeypatch.setattr(cnpj_lookup, "buscar_por_nome", _proibido)

    await _semear_resolvido(session)

    fornecedores = [{"nome_forn": NOME_ENTRADA, "cnpj": None}]
    for f in fornecedores:
        if not f.get("cnpj"):
            fr = await fornecedores_repo.casar(session, f["nome_forn"])
            if fr:
                f["cnpj"] = fr.cnpj
                f["cnpj_pendente"] = False
                f["cnpj_confirmado"] = True

    assert fornecedores[0]["cnpj"] == CNPJ_X
    assert fornecedores[0]["cnpj_pendente"] is False


async def test_registrar_alias_idempotente(session):
    await fornecedores_repo.registrar_alias(session, NOME_ENTRADA, CNPJ_X)
    # Registrar a mesma grafia de novo não duplica nem quebra.
    await fornecedores_repo.registrar_alias(session, NOME_ENTRADA, CNPJ_X)

    res = await session.execute(FornecedorAlias.__table__.select())
    linhas = res.fetchall()
    assert len(linhas) == 1


async def test_registrar_alias_atualiza_cnpj_sem_duplicar(session):
    await fornecedores_repo.registrar_alias(session, NOME_ENTRADA, CNPJ_X)
    novo_cnpj = "99887766000155"
    # Correção: mesma grafia, CNPJ diferente. Atualiza, não cria segunda linha.
    await fornecedores_repo.registrar_alias(session, NOME_ENTRADA, novo_cnpj)

    res = await session.execute(FornecedorAlias.__table__.select())
    linhas = res.fetchall()
    assert len(linhas) == 1
    forn = await fornecedores_repo.casar(session, NOME_ENTRADA)
    # Sem Fornecedor para o novo CNPJ, casa pelo CNPJ do alias mesmo assim.
    assert forn is not None
    assert forn.cnpj == novo_cnpj


@pytest.mark.parametrize("nome,cnpj", [("", CNPJ_X), (NOME_ENTRADA, ""), ("   ", CNPJ_X)])
async def test_registrar_alias_tolera_entrada_vazia(session, nome, cnpj):
    await fornecedores_repo.registrar_alias(session, nome, cnpj)
    res = await session.execute(FornecedorAlias.__table__.select())
    assert res.fetchall() == []


async def test_fallback_casa_pela_razao_social(session):
    # Sem alias: o casamento ainda funciona pela razão social normalizada do Fornecedor.
    await fornecedores_repo.upsert(session, CNPJ_X, NOME_OFICIAL, "cnpja")

    forn = await fornecedores_repo.casar(session, NOME_OFICIAL)
    assert forn is not None
    assert forn.cnpj == CNPJ_X

    # Mas a grafia do arquivo (que NÃO bate com a razão social) não casa sem alias.
    assert await fornecedores_repo.casar(session, NOME_ENTRADA) is None


async def test_alias_tem_prioridade_sobre_razao_social(session):
    # Outro Fornecedor cuja razão social bate com a grafia de entrada de um terceiro.
    await fornecedores_repo.upsert(session, "11111111000111", NOME_ENTRADA, "manual")
    # Mas existe alias apontando a grafia para o CNPJ correto.
    await fornecedores_repo.upsert(session, CNPJ_X, NOME_OFICIAL, "cnpja")
    await fornecedores_repo.registrar_alias(session, NOME_ENTRADA, CNPJ_X)

    forn = await fornecedores_repo.casar(session, NOME_ENTRADA)
    assert forn.cnpj == CNPJ_X  # alias ganha do match por razão social
