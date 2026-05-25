"""Isolamento multi-tenant (CRÍTICO): com auth_enabled=True, escritório A não enxerga
dados de B; admin enxerga de todos; com auth_enabled=False o comportamento atual fica intacto.

Testa vazamento explicitamente nos três vetores: análises, fornecedores (cache global com
visão isolada) e carteira M02 (monitorados).
"""
from fastapi.testclient import TestClient

from app.auth import service
from app.main import app
from app.modules.modulo01 import analises_repo, fornecedores_repo
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
