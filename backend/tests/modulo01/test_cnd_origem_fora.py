"""Progresso da CND sinaliza quando a falha é por a FONTE (Receita/PGFN) estar fora do ar.

O lote conta em `cnd_progresso["origem_indisponivel"]` só as falhas por origem indisponível
(code 615 e afins), não as falhas comuns (CNPJ inválido, etc.). Serve para o frontend avisar
"a Receita Federal está temporariamente fora do ar" em vez de "defeito do sistema".
"""
import pytest

from app.modules.modulo01 import cnd
from app.modules.modulo01.jobs import store


@pytest.fixture(autouse=True)
def _isola_efeitos(monkeypatch):
    # Neutraliza I/O de banco do fim do lote; o foco é o contador no progresso.
    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(cnd, "_sincronizar_historico", _noop)
    monkeypatch.setattr(cnd.fornecedores_repo, "registrar_cnd", _noop)
    # Sempre há saldo no teto (não é o que este teste exercita).
    monkeypatch.setattr(cnd.budget, "consumir", lambda servico, n=1: True)


def _job_com(fornecedores: list[dict]) -> str:
    return store.criar({"status": "parsed", "fornecedores": fornecedores, "metadados": {}})


async def test_origem_fora_conta_no_progresso(monkeypatch):
    # Um CNPJ falha por origem fora (615), outro retorna negativa: origem_indisponivel == 1.
    async def _fake_cnd(cnpj, client):
        if cnpj == "11111111111111":
            return {"status": cnd.FALHA, "descricao": "Origem fora", "origem_fora": True}
        return {"status": cnd.NEGATIVA, "origem_fora": False}

    monkeypatch.setattr(cnd, "consultar_cnd", _fake_cnd)

    job_id = _job_com([
        {"cod_forn": "0001", "cnpj": "11111111111111", "nome_forn": "A"},
        {"cod_forn": "0002", "cnpj": "22222222222222", "nome_forn": "B"},
    ])
    alvos = [("0001", "11111111111111"), ("0002", "22222222222222")]
    await cnd._processar(job_id, alvos, total=2)

    prog = store.obter(job_id)["cnd_progresso"]
    assert prog["consultados"] == 2
    assert prog["falhas"] == 1
    assert prog["origem_indisponivel"] == 1
    assert prog["status"] == "concluido"
    store.remover(job_id)


async def test_falha_comum_nao_conta_como_origem_fora(monkeypatch):
    # Falha que NÃO é origem fora (ex.: CNPJ inválido): conta em falhas, não em origem.
    async def _fake_cnd(cnpj, client):
        return {"status": cnd.FALHA, "descricao": "CNPJ inválido", "origem_fora": False}

    monkeypatch.setattr(cnd, "consultar_cnd", _fake_cnd)

    job_id = _job_com([{"cod_forn": "0001", "cnpj": "11111111111111", "nome_forn": "A"}])
    await cnd._processar(job_id, [("0001", "11111111111111")], total=1)

    prog = store.obter(job_id)["cnd_progresso"]
    assert prog["falhas"] == 1
    assert prog["origem_indisponivel"] == 0
    store.remover(job_id)


async def test_cobradas_conta_billable_inclusive_falha(monkeypatch):
    # O contador de custo (cobradas) segue o billable: sucesso cobra, falha 611 cobra,
    # falha sem cobrança (615) não. Audit trail reflete a fatura real, não "status != FALHA".
    async def _fake_cnd(cnpj, client):
        if cnpj == "11111111111111":  # sucesso, faturado
            return {"status": cnd.NEGATIVA, "origem_fora": False, "cobrada": True}
        if cnpj == "22222222222222":  # falha que cobra (611)
            return {"status": cnd.FALHA, "origem_fora": True, "cobrada": True}
        return {"status": cnd.FALHA, "origem_fora": True, "cobrada": False}  # falha não faturada

    monkeypatch.setattr(cnd, "consultar_cnd", _fake_cnd)

    job_id = _job_com([
        {"cod_forn": "0001", "cnpj": "11111111111111", "nome_forn": "A"},
        {"cod_forn": "0002", "cnpj": "22222222222222", "nome_forn": "B"},
        {"cod_forn": "0003", "cnpj": "33333333333333", "nome_forn": "C"},
    ])
    alvos = [("0001", "11111111111111"), ("0002", "22222222222222"), ("0003", "33333333333333")]
    await cnd._processar(job_id, alvos, total=3)

    prog = store.obter(job_id)["cnd_progresso"]
    assert prog["consultados"] == 3
    assert prog["falhas"] == 2
    assert prog["cobradas"] == 2  # 1 sucesso + 1 falha-611; a falha não faturada não conta
    store.remover(job_id)
