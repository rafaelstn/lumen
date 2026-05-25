"""Testes do enriquecimento de CNPJ em background (espelha o padrão da CND).

cnpj_lookup.buscar_por_nome é mockado — nunca chama a CNPJá. O budget e a persistência
(banco/audit) são stubados para o teste rodar isolado e rápido. A task de background é
drenada com um helper que cede o loop até o progresso ficar 'concluido'.
"""
import asyncio

import pytest

from app.config import settings
from app.modules.modulo01 import budget, enriquecimento
from app.modules.modulo01 import cnpj_lookup as cl
from app.modules.modulo01.jobs import store


def _job(n_pendentes: int) -> str:
    """Cria um job com n fornecedores pendentes (sem CNPJ) + 1 já casado."""
    forns = [
        {"cod_forn": f"F{i}", "nome_forn": f"FORN {i}", "cnpj": None} for i in range(n_pendentes)
    ]
    forns.append({"cod_forn": "JA", "nome_forn": "JA CASADO", "cnpj": "37335118000180"})
    return store.criar({"status": "parsed", "fornecedores": forns, "resumo": {}, "metadados": {}})


async def _drenar(job_id: str) -> dict:
    """Aguarda a task de background do enriquecimento terminar e devolve o progresso final.

    Aguarda a própria task (não faz poll com asyncio.sleep) para não interferir com o sleep
    do throttle, que alguns testes neutralizam ou contam.
    """
    await asyncio.gather(*list(enriquecimento._tasks))
    return store.obter(job_id)["enriquecimento_progresso"]


@pytest.fixture(autouse=True)
def _isola(monkeypatch):
    """Budget infinito, throttle instantâneo e persistência neutralizada (sem banco/audit).

    O throttle fica instantâneo via rate altíssimo (intervalo ~0), sem mexer no asyncio.sleep
    global — neutralizar cl.asyncio.sleep corromperia o sleep de toda a suíte.
    """
    monkeypatch.setattr(budget, "consumir", lambda servico, n=1: True)
    monkeypatch.setattr(budget, "devolver", lambda servico, n=1: None)
    monkeypatch.setattr(settings, "cnpj_rate_por_min", 100000)
    monkeypatch.setattr(settings, "cnpj_rate_folga", 0.0)

    async def _persist_noop(job_id, achados, nao_achados, consumidos):
        _persist_noop.calls.append((dict(achados), dict(nao_achados), consumidos))

    _persist_noop.calls = []
    monkeypatch.setattr(enriquecimento, "_persistir", _persist_noop)

    # Sem banco nestes testes: a lista de já-tentados é vazia (não pula ninguém). Os testes
    # específicos de skip/forcar montam seu próprio comportamento.
    async def _sem_tentativas(escritorio_id):
        return set()

    monkeypatch.setattr(enriquecimento, "_nomes_ja_tentados", _sem_tentativas)
    return _persist_noop


def _match(confianca: str):
    async def _fake(nome, uf, client, throttle=None):
        if throttle is not None:
            await throttle.aguardar()
        return {
            "cnpj": "37335118000180",
            "nome_oficial": f"{nome} OFICIAL",
            "confianca": confianca,
            "n_candidatos": 1,
        }

    return _fake


async def test_disparo_marca_em_andamento_e_conclui(monkeypatch):
    monkeypatch.setattr(cl, "buscar_por_nome", _match(cl.CONF_ALTA))
    job_id = _job(3)

    res = await enriquecimento.iniciar_enriquecimento_job(job_id, settings.cnpj_lookup_limite_max)
    assert res == {"status": "iniciado", "total": 3}
    # Logo após o disparo, antes de ceder o loop, já está em_andamento.
    assert store.obter(job_id)["enriquecimento_progresso"]["status"] == "em_andamento"

    prog = await _drenar(job_id)
    assert prog["status"] == "concluido"
    assert prog["processados"] == 3
    assert prog["confirmados"] == 3
    assert prog["percentual"] == 100.0
    # Os pendentes receberam o CNPJ confirmado no job.
    forns = store.obter(job_id)["fornecedores"]
    pendentes = [f for f in forns if f["cod_forn"].startswith("F")]
    assert all(f["cnpj"] == "37335118000180" and f["cnpj_confirmado"] for f in pendentes)


async def test_contagens_por_confianca(monkeypatch):
    respostas = [cl.CONF_ALTA, cl.CONF_BAIXA, cl.CONF_AMBIGUO, cl.CONF_NAO_ENCONTRADO]
    seq = iter(respostas)

    async def _fake(nome, uf, client, throttle=None):
        if throttle is not None:
            await throttle.aguardar()
        conf = next(seq)
        return {"cnpj": "37335118000180" if conf in (cl.CONF_ALTA, cl.CONF_BAIXA) else None,
                "nome_oficial": "X", "confianca": conf, "n_candidatos": 1}

    monkeypatch.setattr(cl, "buscar_por_nome", _fake)
    job_id = _job(4)
    await enriquecimento.iniciar_enriquecimento_job(job_id, settings.cnpj_lookup_limite_max)
    prog = await _drenar(job_id)
    assert prog["processados"] == 4
    assert prog["confirmados"] == 1
    assert prog["baixa_confianca"] == 1
    assert prog["ambiguos"] == 1
    assert prog["nao_encontrados"] == 1


async def test_idempotencia_nao_dispara_duas_vezes(monkeypatch):
    # Mantém a primeira task viva (busca lenta) e tenta disparar de novo.
    liberar = asyncio.Event()

    async def _lento(nome, uf, client, throttle=None):
        await liberar.wait()
        return {"cnpj": "37335118000180", "nome_oficial": "X", "confianca": cl.CONF_ALTA, "n_candidatos": 1}

    monkeypatch.setattr(cl, "buscar_por_nome", _lento)
    job_id = _job(2)

    r1 = await enriquecimento.iniciar_enriquecimento_job(job_id, settings.cnpj_lookup_limite_max)
    assert r1["status"] == "iniciado"
    await asyncio.sleep(0)  # deixa a task começar e travar na busca lenta

    r2 = await enriquecimento.iniciar_enriquecimento_job(job_id, settings.cnpj_lookup_limite_max)
    assert r2["status"] == "ja_em_andamento"

    liberar.set()
    await _drenar(job_id)


async def test_throttle_respeitado(monkeypatch):
    # Conta as dormidas do throttle: 5 buscas => 4 esperas (a primeira não espera).
    # Neutraliza só o sleep do throttle (objeto _Throttle), sem tocar no asyncio.sleep global,
    # senão o gather de _drenar não cederia o loop. _drenar aguarda a task, não usa sleep.
    dormidas = []

    async def _conta_sleep(s):
        dormidas.append(s)

    monkeypatch.setattr(cl.asyncio, "sleep", _conta_sleep)
    monkeypatch.setattr(settings, "cnpj_rate_por_min", 10)
    monkeypatch.setattr(settings, "cnpj_rate_folga", 0.0)
    monkeypatch.setattr(cl, "buscar_por_nome", _match(cl.CONF_ALTA))

    job_id = _job(5)
    await enriquecimento.iniciar_enriquecimento_job(job_id, settings.cnpj_lookup_limite_max)
    # Aguarda a task explicitamente (gather), sem poll por sleep que aqui está neutralizado.
    await asyncio.gather(*list(enriquecimento._tasks))
    assert len(dormidas) == 4
    assert all(abs(d - 6.0) < 0.5 for d in dormidas)  # 60/10 por chamada


async def test_teto_de_seguranca_limita_pendentes(monkeypatch):
    monkeypatch.setattr(cl, "buscar_por_nome", _match(cl.CONF_ALTA))
    job_id = _job(10)
    res = await enriquecimento.iniciar_enriquecimento_job(job_id, 4)  # teto por job = 4
    assert res["total"] == 4
    prog = await _drenar(job_id)
    assert prog["processados"] == 4
    # 6 seguem pendentes.
    forns = store.obter(job_id)["fornecedores"]
    assert sum(1 for f in forns if f["cod_forn"].startswith("F") and not f["cnpj"]) == 6


async def test_rate_limit_para_lote_e_estorna(monkeypatch):
    estornos = []
    monkeypatch.setattr(budget, "devolver", lambda servico, n=1: estornos.append(n))

    chamadas = {"n": 0}

    async def _fake(nome, uf, client, throttle=None):
        chamadas["n"] += 1
        if chamadas["n"] == 2:
            raise cl.RateLimitError("rate")
        return {"cnpj": "37335118000180", "nome_oficial": "X", "confianca": cl.CONF_ALTA, "n_candidatos": 1}

    monkeypatch.setattr(cl, "buscar_por_nome", _fake)
    job_id = _job(5)
    await enriquecimento.iniciar_enriquecimento_job(job_id, settings.cnpj_lookup_limite_max)
    prog = await _drenar(job_id)
    assert prog["limite_taxa_atingido"] is True
    assert prog["processados"] == 1  # parou na 2a busca (rate limit)
    assert estornos == [1]  # estornou o crédito reservado da busca não feita


async def test_persistencia_recebe_achados_e_consumidos(monkeypatch, _isola):
    monkeypatch.setattr(cl, "buscar_por_nome", _match(cl.CONF_ALTA))
    job_id = _job(2)
    await enriquecimento.iniciar_enriquecimento_job(job_id, settings.cnpj_lookup_limite_max)
    await _drenar(job_id)
    # _persistir foi chamado uma vez com 2 achados, 0 não-achados e 2 buscas consumidas.
    achados, nao_achados, consumidos = _isola.calls[-1]
    assert len(achados) == 2
    assert nao_achados == {}
    assert consumidos == 2


async def test_job_inexistente():
    res = await enriquecimento.iniciar_enriquecimento_job("nao-existe", 10)
    assert res == {"status": "nao_encontrado"}


async def test_sem_pendentes_conclui_imediato(monkeypatch):
    monkeypatch.setattr(cl, "buscar_por_nome", _match(cl.CONF_ALTA))
    job_id = store.criar(
        {"status": "parsed", "fornecedores": [{"cod_forn": "JA", "nome_forn": "X", "cnpj": "37335118000180"}],
         "resumo": {}, "metadados": {}}
    )
    res = await enriquecimento.iniciar_enriquecimento_job(job_id, settings.cnpj_lookup_limite_max)
    assert res == {"status": "iniciado", "total": 0}
    assert store.obter(job_id)["enriquecimento_progresso"]["status"] == "concluido"
