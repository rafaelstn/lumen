"""Auth: signup, login, /me, seed idempotente do admin, endpoint admin (403/200).

Cobre os dois modos da flag onde faz sentido. A isolação multi-tenant tem arquivo próprio.
"""
from fastapi.testclient import TestClient

from app.auth import service
from app.main import app


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_signup_cria_escritorio_e_usuario_e_devolve_token(factory):
    client = TestClient(app)
    resp = client.post(
        "/api/auth/signup",
        json={"nome_escritorio": "Contabil A", "email": "a@a.com", "senha": "senha12345"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["usuario"]["email"] == "a@a.com"
    assert body["usuario"]["role"] == "escritorio"
    assert "senha_hash" not in body["usuario"]
    assert body["token"]["access_token"]
    assert body["token"]["token_type"] == "bearer"


def test_signup_email_duplicado_409(factory):
    client = TestClient(app)
    payload = {"nome_escritorio": "Escritorio Dup", "email": "dup@a.com", "senha": "senha12345"}
    assert client.post("/api/auth/signup", json=payload).status_code == 201
    assert client.post("/api/auth/signup", json=payload).status_code == 409


def test_signup_senha_curta_422(factory):
    client = TestClient(app)
    resp = client.post(
        "/api/auth/signup",
        json={"nome_escritorio": "X", "email": "curta@a.com", "senha": "1234"},
    )
    assert resp.status_code == 422


def test_login_ok_e_senha_errada_401_generico(factory):
    client = TestClient(app)
    client.post(
        "/api/auth/signup",
        json={"nome_escritorio": "Escritorio B", "email": "b@b.com", "senha": "senha12345"},
    )
    ok = client.post("/api/auth/login", json={"email": "b@b.com", "senha": "senha12345"})
    assert ok.status_code == 200
    assert ok.json()["access_token"]

    errada = client.post("/api/auth/login", json={"email": "b@b.com", "senha": "errada99999"})
    assert errada.status_code == 401
    inexistente = client.post("/api/auth/login", json={"email": "nao@existe.com", "senha": "x12345678"})
    assert inexistente.status_code == 401
    # Mensagem genérica idêntica: não revela se o e-mail existe.
    assert errada.json()["detail"] == inexistente.json()["detail"]


def test_me_com_token_valido(factory, auth_on):
    client = TestClient(app)
    token = client.post(
        "/api/auth/signup",
        json={"nome_escritorio": "Escritorio C", "email": "c@c.com", "senha": "senha12345"},
    ).json()["token"]["access_token"]

    resp = client.get("/api/auth/me", headers=_bearer(token))
    assert resp.status_code == 200
    assert resp.json()["email"] == "c@c.com"
    assert "senha_hash" not in resp.json()


def test_me_sem_token_com_auth_on_401(factory, auth_on):
    client = TestClient(app)
    assert client.get("/api/auth/me").status_code == 401


# --- seed do admin ----------------------------------------------------------------


async def test_seed_admin_idempotente(factory):
    async with factory() as session:
        criou1 = await service.seed_admin(session, "admin@lumen.com", "adminsenha123")
    async with factory() as session:
        criou2 = await service.seed_admin(session, "admin@lumen.com", "adminsenha123")
    assert criou1 is True
    assert criou2 is False


async def test_seed_admin_sem_env_nao_cria(factory):
    async with factory() as session:
        assert await service.seed_admin(session, "", "") is False


# --- endpoint admin (role) --------------------------------------------------------


def _login(client, email, senha):
    return client.post("/api/auth/login", json={"email": email, "senha": senha}).json()["access_token"]


def test_admin_escritorios_403_para_nao_admin(factory, auth_on):
    client = TestClient(app)
    token = client.post(
        "/api/auth/signup",
        json={"nome_escritorio": "Comum", "email": "comum@a.com", "senha": "senha12345"},
    ).json()["token"]["access_token"]
    assert client.get("/api/admin/escritorios", headers=_bearer(token)).status_code == 403


async def test_admin_escritorios_200_para_admin(factory, auth_on):
    # Semeia o admin direto no banco e loga.
    async with factory() as session:
        await service.seed_admin(session, "root@lumen.com", "rootsenha123")
    client = TestClient(app)
    client.post(
        "/api/auth/signup",
        json={"nome_escritorio": "Outro", "email": "outro@a.com", "senha": "senha12345"},
    )
    token = _login(client, "root@lumen.com", "rootsenha123")
    resp = client.get("/api/admin/escritorios", headers=_bearer(token))
    assert resp.status_code == 200
    nomes = [e["nome"] for e in resp.json()]
    # Admin vê o escritório "Administração" + o "Outro" recém-criado.
    assert "Administração" in nomes
    assert "Outro" in nomes


def test_admin_escritorios_403_com_auth_off(factory, auth_off):
    # Com a flag desligada, o contexto é anônimo (não-admin): o endpoint admin fica fechado.
    client = TestClient(app)
    assert client.get("/api/admin/escritorios").status_code == 403
