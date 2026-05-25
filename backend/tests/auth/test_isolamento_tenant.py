"""Isolamento multi-tenant (CRÍTICO): com auth_enabled=True, escritório A não enxerga
dados de B; admin enxerga de todos; com auth_enabled=False o comportamento atual fica intacto.

Testa vazamento explicitamente nos três vetores: análises, fornecedores (cache global com
visão isolada) e carteira M02 (monitorados).
"""
from fastapi.testclient import TestClient

from app.auth import service
from app.main import app
from app.modules.consumo import repo as consumo_repo
from app.modules.consumo.models import SERVICO_CNPJ
from app.modules.modulo01 import analises_repo, fornecedores_repo
from app.modules.modulo01.jobs import store
from app.modules.modulo02 import repo as m02_repo


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _signup(client, nome, email) -> dict:
    return client.post(
        "/api/auth/signup",
        json={"nome_escritorio": nome, "email": email, "senha": "senha12345"},
    ).json()


async def _seed_analise(factory, escritorio_id: str, analise_id: str, cliente: str) -> None:
    async with factory() as s:
        await analises_repo.salvar(
            s, analise_id, {"escritorio_id": escritorio_id, "metadados": {"cliente": cliente}, "resumo": {}, "fornecedores": []}
        )


async def _seed_fornecedor(factory, cnpj: str, razao: str, escritorio_id: str | None) -> None:
    async with factory() as s:
        await fornecedores_repo.salvar_cadastro(s, {"cnpj": cnpj, "razao_social": razao}, "cnpja")
        if escritorio_id:
            await fornecedores_repo.associar_escritorio(s, escritorio_id, cnpj)


async def _seed_monitorado(factory, escritorio_id: str, cnpj: str, razao: str) -> None:
    async with factory() as s:
        await m02_repo.upsert_monitorado(
            s, escritorio_id,
            {"cnpj": cnpj, "razao_social": razao, "score": 50, "status_cnd": "NEGATIVA",
             "faixa": "MEDIO", "componentes": {}},
        )


# --- análises ----------------------------------------------------------------------


async def test_analises_nao_vazam_entre_escritorios(factory, auth_on):
    client = TestClient(app)
    a = _signup(client, "Esc A", "a@a.com")
    b = _signup(client, "Esc B", "b@b.com")
    await _seed_analise(factory, a["usuario"]["escritorio_id"], "an-a", "Cliente A")
    await _seed_analise(factory, b["usuario"]["escritorio_id"], "an-b", "Cliente B")

    resp_a = client.get("/api/modulo01/analises", headers=_bearer(a["token"]["access_token"]))
    ids_a = [x["id"] for x in resp_a.json()["analises"]]
    assert ids_a == ["an-a"]  # A só vê a própria

    # A não consegue reabrir nem apagar a análise de B (404, não vaza).
    assert client.get("/api/modulo01/analise/an-b", headers=_bearer(a["token"]["access_token"])).status_code == 404
    assert client.delete("/api/modulo01/analise/an-b", headers=_bearer(a["token"]["access_token"])).status_code == 404


async def test_admin_ve_analises_de_todos(factory, auth_on):
    client = TestClient(app)
    a = _signup(client, "Esc A", "a2@a.com")
    b = _signup(client, "Esc B", "b2@b.com")
    await _seed_analise(factory, a["usuario"]["escritorio_id"], "an-a2", "Cliente A")
    await _seed_analise(factory, b["usuario"]["escritorio_id"], "an-b2", "Cliente B")
    async with factory() as s:
        await service.seed_admin(s, "root@lumen.com", "rootsenha123")
    token = client.post("/api/auth/login", json={"email": "root@lumen.com", "senha": "rootsenha123"}).json()["access_token"]

    ids = {x["id"] for x in client.get("/api/modulo01/analises", headers=_bearer(token)).json()["analises"]}
    assert {"an-a2", "an-b2"} <= ids


async def test_analises_auth_off_comportamento_atual(factory, auth_off):
    # Sem token, contexto anônimo (escritório default): vê o que está no default.
    client = TestClient(app)
    from app.config import settings

    await _seed_analise(factory, settings.escritorio_default_id, "an-default", "Cliente Default")
    resp = client.get("/api/modulo01/analises")
    assert resp.status_code == 200
    assert [x["id"] for x in resp.json()["analises"]] == ["an-default"]


# --- fornecedores (cache global / visão isolada) ----------------------------------


async def test_fornecedores_visao_isolada(factory, auth_on):
    client = TestClient(app)
    a = _signup(client, "Esc A", "fa@a.com")
    b = _signup(client, "Esc B", "fb@b.com")
    esc_a = a["usuario"]["escritorio_id"]
    esc_b = b["usuario"]["escritorio_id"]
    # Cache global tem os dois; A associou só o seu, B só o dele.
    await _seed_fornecedor(factory, "11111111111111", "FORN A LTDA", esc_a)
    await _seed_fornecedor(factory, "22222222222222", "FORN B LTDA", esc_b)

    cnpjs_a = {f["cnpj"] for f in client.get("/api/modulo01/fornecedores", headers=_bearer(a["token"]["access_token"])).json()["resultados"]}
    assert cnpjs_a == {"11111111111111"}  # A não vê o fornecedor de B

    cnpjs_b = {f["cnpj"] for f in client.get("/api/modulo01/fornecedores", headers=_bearer(b["token"]["access_token"])).json()["resultados"]}
    assert cnpjs_b == {"22222222222222"}


async def test_admin_ve_todos_fornecedores(factory, auth_on):
    client = TestClient(app)
    a = _signup(client, "Esc A", "fa2@a.com")
    await _seed_fornecedor(factory, "33333333333333", "FORN A", a["usuario"]["escritorio_id"])
    await _seed_fornecedor(factory, "44444444444444", "FORN ORFAO", None)  # sem associação
    async with factory() as s:
        await service.seed_admin(s, "root2@lumen.com", "rootsenha123")
    token = client.post("/api/auth/login", json={"email": "root2@lumen.com", "senha": "rootsenha123"}).json()["access_token"]

    cnpjs = {f["cnpj"] for f in client.get("/api/modulo01/fornecedores", headers=_bearer(token)).json()["resultados"]}
    assert {"33333333333333", "44444444444444"} <= cnpjs


async def test_fornecedores_auth_off_ve_todos(factory, auth_off):
    client = TestClient(app)
    await _seed_fornecedor(factory, "55555555555555", "FORN X", None)
    await _seed_fornecedor(factory, "66666666666666", "FORN Y", None)
    cnpjs = {f["cnpj"] for f in client.get("/api/modulo01/fornecedores").json()["resultados"]}
    assert {"55555555555555", "66666666666666"} <= cnpjs


# --- carteira M02 ------------------------------------------------------------------


async def test_carteira_m02_nao_vaza(factory, auth_on):
    client = TestClient(app)
    a = _signup(client, "Esc A", "ma@a.com")
    b = _signup(client, "Esc B", "mb@b.com")
    await _seed_monitorado(factory, a["usuario"]["escritorio_id"], "77777777777777", "MON A")
    await _seed_monitorado(factory, b["usuario"]["escritorio_id"], "88888888888888", "MON B")

    cnpjs_a = {m["cnpj"] for m in client.get("/api/modulo02/monitorados", headers=_bearer(a["token"]["access_token"])).json()}
    assert cnpjs_a == {"77777777777777"}  # A não vê a carteira de B


# --- alertas (gap coberto) ----------------------------------------------------------


async def test_alertas_nao_vazam_entre_escritorios(factory, auth_on):
    client = TestClient(app)
    a = _signup(client, "Esc A", "ala@a.com")
    b = _signup(client, "Esc B", "alb@b.com")
    esc_a = a["usuario"]["escritorio_id"]
    esc_b = b["usuario"]["escritorio_id"]
    # Cria um monitorado em cada escritório (o alerta precisa de fornecedor_id válido).
    await _seed_monitorado(factory, esc_a, "10000000000001", "MON A")
    await _seed_monitorado(factory, esc_b, "10000000000002", "MON B")
    async with factory() as s:
        fa = await m02_repo.obter_por_cnpj(s, esc_a, "10000000000001")
        fb = await m02_repo.obter_por_cnpj(s, esc_b, "10000000000002")
        await m02_repo.criar_alerta(s, esc_a, fa.id, "SCORE_CRITICO", "alerta A")
        await m02_repo.criar_alerta(s, esc_b, fb.id, "SCORE_CRITICO", "alerta B")

    msgs_a = {x["mensagem"] for x in client.get("/api/modulo02/alertas", headers=_bearer(a["token"]["access_token"])).json()}
    assert msgs_a == {"alerta A"}  # A não vê o alerta de B


async def test_admin_ve_alertas_de_todos(factory, auth_on):
    client = TestClient(app)
    a = _signup(client, "Esc A", "ala2@a.com")
    b = _signup(client, "Esc B", "alb2@b.com")
    esc_a = a["usuario"]["escritorio_id"]
    esc_b = b["usuario"]["escritorio_id"]
    await _seed_monitorado(factory, esc_a, "10000000000003", "MON A")
    await _seed_monitorado(factory, esc_b, "10000000000004", "MON B")
    async with factory() as s:
        fa = await m02_repo.obter_por_cnpj(s, esc_a, "10000000000003")
        fb = await m02_repo.obter_por_cnpj(s, esc_b, "10000000000004")
        await m02_repo.criar_alerta(s, esc_a, fa.id, "SCORE_CRITICO", "alerta A2")
        await m02_repo.criar_alerta(s, esc_b, fb.id, "SCORE_CRITICO", "alerta B2")
        await service.seed_admin(s, "rootal@lumen.com", "rootsenha123")
    token = client.post("/api/auth/login", json={"email": "rootal@lumen.com", "senha": "rootsenha123"}).json()["access_token"]

    msgs = {x["mensagem"] for x in client.get("/api/modulo02/alertas", headers=_bearer(token)).json()}
    assert {"alerta A2", "alerta B2"} <= msgs


# --- consumo / histórico (gap coberto) ---------------------------------------------


async def test_consumo_historico_nao_vaza_entre_escritorios(factory, auth_on):
    client = TestClient(app)
    a = _signup(client, "Esc A", "ca@a.com")
    b = _signup(client, "Esc B", "cb@b.com")
    esc_a = a["usuario"]["escritorio_id"]
    esc_b = b["usuario"]["escritorio_id"]
    # Audit trail de consumo em cada escritório (sessão própria do repo).
    async with factory() as _:  # garante a factory monkeypatchada ativa
        await consumo_repo.registrar_consulta(
            escritorio_id=esc_a, modulo="modulo02", servico=SERVICO_CNPJ,
            operacao="due_diligence", quantidade=3, creditos_consumidos=6, contexto="A",
        )
        await consumo_repo.registrar_consulta(
            escritorio_id=esc_b, modulo="modulo02", servico=SERVICO_CNPJ,
            operacao="due_diligence", quantidade=7, creditos_consumidos=14, contexto="B",
        )

    hist_a = client.get("/api/consultas/historico", headers=_bearer(a["token"]["access_token"])).json()
    # A só vê o próprio consumo: 1 registro de 6 créditos (não enxerga os 14 de B).
    assert len(hist_a["itens"]) == 1, hist_a
    assert hist_a["totais"]["creditos_consumidos"] == 6, hist_a


# --- 401 sem token (regressão da flag on) -------------------------------------------


def test_endpoints_de_dados_exigem_token_com_auth_on(factory, auth_on):
    client = TestClient(app)
    # Sem Authorization, todo endpoint de dado retorna 401 (não vaza, não cai no default).
    assert client.get("/api/modulo01/analises").status_code == 401
    assert client.get("/api/modulo01/fornecedores").status_code == 401
    assert client.get("/api/modulo02/monitorados").status_code == 401
    assert client.get("/api/modulo02/alertas").status_code == 401
    assert client.get("/api/consultas/historico").status_code == 401


# --- cnpj-manual: posse do job (IDOR de escrita) ------------------------------------


async def test_cnpj_manual_nao_muta_job_de_outro_escritorio(factory, auth_on):
    """Com auth on, A não pode definir o CNPJ manual de um job que pertence a B (404)."""
    client = TestClient(app)
    a = _signup(client, "Esc A", "ja@a.com")
    b = _signup(client, "Esc B", "jb@b.com")
    esc_b = b["usuario"]["escritorio_id"]
    # Job vivo no store, dono = B, com um fornecedor pendente de CNPJ.
    job_id = store.criar(
        {
            "status": "parsed",
            "escritorio_id": esc_b,
            "metadados": {},
            "resumo": {},
            "fornecedores": [{"cod_forn": "F1", "nome_forn": "ACME", "cnpj": None}],
        }
    )
    resp = client.post(
        f"/api/modulo01/cnpj-manual/{job_id}",
        json={"cod_forn": "F1", "cnpj": "11444777000161", "razao_social": "INVASOR"},
        headers=_bearer(a["token"]["access_token"]),
    )
    assert resp.status_code == 404  # A não enxerga/altera o job de B
    # O job de B continua intacto.
    assert store.obter(job_id)["fornecedores"][0]["cnpj"] is None
    store.remover(job_id)


# --- leitura de job no store: posse (IDOR de leitura) -------------------------------


async def test_leitura_job_em_memoria_nao_vaza(factory, auth_on):
    """A não lê resultado/progresso/relatório de um job vivo que pertence a B (404).

    A posse é checada ANTES de montar o response, então o 404 do intruso independe do shape
    do payload do job. (Os vetores de leitura compartilham o mesmo _checar_posse_job.)
    """
    client = TestClient(app)
    a = _signup(client, "Esc A", "rja@a.com")
    b = _signup(client, "Esc B", "rjb@b.com")
    esc_b = b["usuario"]["escritorio_id"]
    job_id = store.criar(
        {
            "status": "parsed",
            "escritorio_id": esc_b,
            "metadados": {"cliente": "Cliente B"},
            "resumo": {},
            "fornecedores": [],
        }
    )
    tok_a = _bearer(a["token"]["access_token"])
    tok_b = _bearer(b["token"]["access_token"])
    # Intruso (A) leva 404 em cada vetor de leitura do job de B.
    assert client.get(f"/api/modulo01/resultado/{job_id}", headers=tok_a).status_code == 404
    assert client.get(f"/api/modulo01/progresso/{job_id}", headers=tok_a).status_code == 404
    assert client.get(f"/api/modulo01/enriquecimento-progresso/{job_id}", headers=tok_a).status_code == 404
    assert client.get(f"/api/modulo01/relatorio/{job_id}", headers=tok_a).status_code == 404
    # Dono (B) NÃO leva 404 de posse (progresso devolve estado, sem schema rígido).
    assert client.get(f"/api/modulo01/progresso/{job_id}", headers=tok_b).status_code == 200
    store.remover(job_id)


async def test_admin_le_job_de_qualquer_escritorio(factory, auth_on):
    client = TestClient(app)
    a = _signup(client, "Esc A", "rja2@a.com")
    esc_a = a["usuario"]["escritorio_id"]
    job_id = store.criar(
        {"status": "parsed", "escritorio_id": esc_a, "metadados": {}, "resumo": {}, "fornecedores": []}
    )
    async with factory() as s:
        await service.seed_admin(s, "rootrj@lumen.com", "rootsenha123")
    token = client.post("/api/auth/login", json={"email": "rootrj@lumen.com", "senha": "rootsenha123"}).json()["access_token"]
    # Admin não leva 404 de posse (passa pela checagem, filtro_escritorio=None).
    assert client.get(f"/api/modulo01/progresso/{job_id}", headers=_bearer(token)).status_code == 200
    store.remover(job_id)
