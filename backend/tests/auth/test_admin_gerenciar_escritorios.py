"""Gerência admin de escritórios (/api/admin): criar e deletar.

Cobre o contrato dos 2 endpoints novos: criação atômica (escritório + dono que loga),
403 para não-admin, 409 para e-mail duplicado, 422 para payload inválido; e a deleção
em cascata que apaga SÓ os dados do tenant alvo, preservando o cache global de fornecedores,
com as proteções (escritório default / escritório com admin dentro / 404).
"""
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.auth import service
from app.config import settings
from app.main import app
from app.models.analise import Analise
from app.models.escritorio import Escritorio
from app.models.fornecedor import (
    EnriquecimentoTentativa,
    EscritorioFornecedor,
    Fornecedor,
)
from app.models.usuario import ROLE_ADMIN, Usuario
from app.modules.consumo.models import SERVICO_CNPJ, ConsultaLog
from app.modules.modulo02.models import Alerta, FornecedorMonitorado, HistoricoCnd


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _login(client, email, senha):
    return client.post(
        "/api/auth/login", json={"email": email, "senha": senha}
    ).json()["access_token"]


def _id() -> str:
    return str(uuid.uuid4())


async def _seed_admin(factory):
    async with factory() as s:
        await service.seed_admin(s, "root@lumen.com", "rootsenha123")


# --- Criar escritório ---------------------------------------------------------------


async def test_admin_cria_escritorio_aparece_na_lista_e_dono_loga(factory, auth_on):
    await _seed_admin(factory)
    client = TestClient(app)
    token = _login(client, "root@lumen.com", "rootsenha123")

    resp = client.post(
        "/api/admin/escritorios",
        headers=_bearer(token),
        json={"nome": "Escritorio Novo", "email": "dono@novo.com", "senha": "senha12345"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["nome"] == "Escritorio Novo"
    assert body["dono_email"] == "dono@novo.com"
    assert body["dono_role"] == "escritorio"
    assert "senha_hash" not in body
    novo_id = body["id"]

    # Aparece na lista admin de escritórios.
    lista = client.get("/api/admin/escritorios", headers=_bearer(token)).json()
    assert novo_id in {e["id"] for e in lista}

    # O dono consegue logar com a senha definida.
    login = client.post(
        "/api/auth/login", json={"email": "dono@novo.com", "senha": "senha12345"}
    )
    assert login.status_code == 200
    assert login.json()["access_token"]


def test_criar_escritorio_403_para_nao_admin(factory, auth_on):
    client = TestClient(app)
    token = client.post(
        "/api/auth/signup",
        json={"nome_escritorio": "Comum", "email": "comum@a.com", "senha": "senha12345"},
    ).json()["token"]["access_token"]

    resp = client.post(
        "/api/admin/escritorios",
        headers=_bearer(token),
        json={"nome": "Tentativa", "email": "x@x.com", "senha": "senha12345"},
    )
    assert resp.status_code == 403


def test_criar_escritorio_403_com_auth_off(factory, auth_off):
    client = TestClient(app)
    resp = client.post(
        "/api/admin/escritorios",
        json={"nome": "Tentativa", "email": "x@x.com", "senha": "senha12345"},
    )
    assert resp.status_code == 403


async def test_criar_escritorio_email_duplicado_409(factory, auth_on):
    await _seed_admin(factory)
    client = TestClient(app)
    token = _login(client, "root@lumen.com", "rootsenha123")

    payload = {"nome": "Primeiro", "email": "dup@a.com", "senha": "senha12345"}
    assert client.post("/api/admin/escritorios", headers=_bearer(token), json=payload).status_code == 201
    # Segundo com o mesmo e-mail colide.
    resp = client.post(
        "/api/admin/escritorios",
        headers=_bearer(token),
        json={"nome": "Segundo", "email": "dup@a.com", "senha": "outrasenha9"},
    )
    assert resp.status_code == 409


async def test_criar_escritorio_senha_curta_422(factory, auth_on):
    await _seed_admin(factory)
    client = TestClient(app)
    token = _login(client, "root@lumen.com", "rootsenha123")

    resp = client.post(
        "/api/admin/escritorios",
        headers=_bearer(token),
        json={"nome": "Curta", "email": "curta@a.com", "senha": "1234"},
    )
    assert resp.status_code == 422


# --- Deletar escritório -------------------------------------------------------------


async def _semear_escritorio_com_dados(factory):
    """Um escritório comum (alvo) com dados de tenant + cache global compartilhado.

    Outro escritório (vizinho) com seus próprios dados, para checar que a deleção do alvo
    não vaza para ele (isolamento). Devolve (alvo_id, vizinho_id).
    """
    alvo, vizinho = _id(), _id()
    async with factory() as s:
        s.add_all([Escritorio(id=alvo, nome="Alvo"), Escritorio(id=vizinho, nome="Vizinho")])
        s.add_all(
            [
                Analise(id=_id(), escritorio_id=alvo, dados={}),
                Analise(id=_id(), escritorio_id=vizinho, dados={}),
            ]
        )
        s.add_all(
            [
                EscritorioFornecedor(escritorio_id=alvo, cnpj="11111111111111"),
                EscritorioFornecedor(escritorio_id=vizinho, cnpj="11111111111111"),
            ]
        )
        s.add_all(
            [
                EnriquecimentoTentativa(
                    escritorio_id=alvo, nome_normalizado="X", resultado="nao_encontrado"
                ),
                EnriquecimentoTentativa(
                    escritorio_id=vizinho, nome_normalizado="Y", resultado="nao_encontrado"
                ),
            ]
        )
        s.add_all(
            [
                ConsultaLog(
                    escritorio_id=alvo, modulo="modulo01", servico=SERVICO_CNPJ,
                    operacao="enriquecimento", quantidade=1, creditos_consumidos=2,
                    custo_centavos=5,
                ),
                ConsultaLog(
                    escritorio_id=vizinho, modulo="modulo01", servico=SERVICO_CNPJ,
                    operacao="enriquecimento", quantidade=1, creditos_consumidos=2,
                    custo_centavos=5,
                ),
            ]
        )
        # M02 do alvo: monitorado + alerta + histórico.
        mon = FornecedorMonitorado(id=_id(), escritorio_id=alvo, cnpj="11111111111111")
        s.add(mon)
        s.add(Alerta(id=_id(), escritorio_id=alvo, fornecedor_id=mon.id, tipo="SCORE_CRITICO", mensagem="m"))
        s.add(HistoricoCnd(id=_id(), fornecedor_id=mon.id, escritorio_id=alvo, status="NEGATIVA"))
        # Cache GLOBAL (compartilhado): 1 fornecedor que NÃO pode sumir na deleção do alvo.
        s.add(Fornecedor(cnpj="11111111111111", razao_social="Global", nome_normalizado="GLOBAL"))
        await s.commit()
    return alvo, vizinho


async def test_admin_deleta_escritorio_comum_cascata_e_preserva_cache_global(factory, auth_on):
    alvo, vizinho = await _semear_escritorio_com_dados(factory)
    await _seed_admin(factory)
    client = TestClient(app)
    token = _login(client, "root@lumen.com", "rootsenha123")

    resp = client.delete(f"/api/admin/escritorio/{alvo}", headers=_bearer(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == alvo
    assert body["status"] == "removido"
    rem = body["removidos"]
    assert rem["usuarios"] == 0
    assert rem["analises"] == 1
    assert rem["escritorio_fornecedor"] == 1
    assert rem["enriquecimento_tentativa"] == 1
    assert rem["consulta_logs"] == 1
    assert rem["fornecedores_monitorados"] == 1
    assert rem["alertas"] == 1
    assert rem["historico_cnd"] == 1

    # Some da lista admin.
    lista = client.get("/api/admin/escritorios", headers=_bearer(token)).json()
    assert alvo not in {e["id"] for e in lista}

    async with factory() as s:
        # Dados do alvo sumiram.
        assert await s.get(Escritorio, alvo) is None
        assert await s.scalar(select(func.count(Analise.id)).where(Analise.escritorio_id == alvo)) == 0
        assert await s.scalar(
            select(func.count(EscritorioFornecedor.id)).where(EscritorioFornecedor.escritorio_id == alvo)
        ) == 0
        assert await s.scalar(
            select(func.count(ConsultaLog.id)).where(ConsultaLog.escritorio_id == alvo)
        ) == 0
        # Cache GLOBAL de fornecedores permanece (não é por tenant).
        assert await s.scalar(
            select(func.count(Fornecedor.id)).where(Fornecedor.cnpj == "11111111111111")
        ) == 1
        # Isolamento: o vizinho mantém TODOS os seus dados.
        assert await s.get(Escritorio, vizinho) is not None
        assert await s.scalar(select(func.count(Analise.id)).where(Analise.escritorio_id == vizinho)) == 1
        assert await s.scalar(
            select(func.count(EscritorioFornecedor.id)).where(EscritorioFornecedor.escritorio_id == vizinho)
        ) == 1
        assert await s.scalar(
            select(func.count(ConsultaLog.id)).where(ConsultaLog.escritorio_id == vizinho)
        ) == 1


async def test_deletar_escritorio_com_admin_dentro_bloqueado(factory, auth_on):
    await _seed_admin(factory)
    client = TestClient(app)
    token = _login(client, "root@lumen.com", "rootsenha123")

    # Descobre o escritório do admin.
    async with factory() as s:
        admin = await s.scalar(select(Usuario).where(Usuario.role == ROLE_ADMIN))
        escritorio_admin = admin.escritorio_id

    resp = client.delete(f"/api/admin/escritorio/{escritorio_admin}", headers=_bearer(token))
    assert resp.status_code == 400

    # O escritório do admin continua de pé.
    async with factory() as s:
        assert await s.get(Escritorio, escritorio_admin) is not None


async def test_deletar_escritorio_default_bloqueado(factory, auth_on):
    await _seed_admin(factory)
    async with factory() as s:
        s.add(Escritorio(id=settings.escritorio_default_id, nome="Default"))
        await s.commit()
    client = TestClient(app)
    token = _login(client, "root@lumen.com", "rootsenha123")

    resp = client.delete(
        f"/api/admin/escritorio/{settings.escritorio_default_id}", headers=_bearer(token)
    )
    assert resp.status_code == 400
    async with factory() as s:
        assert await s.get(Escritorio, settings.escritorio_default_id) is not None


async def test_deletar_escritorio_inexistente_404(factory, auth_on):
    await _seed_admin(factory)
    client = TestClient(app)
    token = _login(client, "root@lumen.com", "rootsenha123")
    resp = client.delete("/api/admin/escritorio/nao-existe", headers=_bearer(token))
    assert resp.status_code == 404


async def test_deletar_escritorio_403_para_nao_admin(factory, auth_on):
    alvo, _ = await _semear_escritorio_com_dados(factory)
    client = TestClient(app)
    token = client.post(
        "/api/auth/signup",
        json={"nome_escritorio": "Comum", "email": "comum3@a.com", "senha": "senha12345"},
    ).json()["token"]["access_token"]
    resp = client.delete(f"/api/admin/escritorio/{alvo}", headers=_bearer(token))
    assert resp.status_code == 403


def test_deletar_escritorio_403_com_auth_off(factory, auth_off):
    client = TestClient(app)
    assert client.delete("/api/admin/escritorio/qualquer").status_code == 403
