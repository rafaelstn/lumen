"""Reset de ambiente (/api/admin/reset-ambiente): zera dados, preserva contas.

Cobre o contrato do endpoint: apaga TODAS as linhas de análise/consulta/cache (reset global,
ambiente de teste/piloto) mas mantém Usuario e Escritorio intactos (login segue funcionando);
proteção de confirmação textual (400 sem apagar nada se o texto não for exato); 403 para
não-admin e com auth desligado.
"""
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.auth import service
from app.main import app
from app.models.analise import Analise
from app.models.escritorio import Escritorio
from app.models.fornecedor import (
    EnriquecimentoTentativa,
    EscritorioFornecedor,
    Fornecedor,
    FornecedorSocio,
)
from app.models.usuario import ROLE_ADMIN, Usuario
from app.modules.consumo.models import SERVICO_CNPJ, ConsultaLog
from app.modules.modulo01.jobs import store as job_store
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


async def _semear_dados(factory):
    """Popula TODAS as tabelas de dados de dois escritórios distintos.

    O reset é global, então depois nenhuma linha de dado deve sobrar, independente do tenant.
    Devolve (e1, e2) ids dos escritórios criados (que devem PERMANECER).
    """
    e1, e2 = _id(), _id()
    async with factory() as s:
        s.add_all([Escritorio(id=e1, nome="Um"), Escritorio(id=e2, nome="Dois")])
        s.add_all(
            [
                Analise(id=_id(), escritorio_id=e1, dados={}),
                Analise(id=_id(), escritorio_id=e2, dados={}),
            ]
        )
        s.add_all(
            [
                EscritorioFornecedor(escritorio_id=e1, cnpj="11111111111111"),
                EscritorioFornecedor(escritorio_id=e2, cnpj="22222222222222"),
            ]
        )
        s.add_all(
            [
                EnriquecimentoTentativa(escritorio_id=e1, nome_normalizado="X", resultado="nao_encontrado"),
                EnriquecimentoTentativa(escritorio_id=e2, nome_normalizado="Y", resultado="ambiguo"),
            ]
        )
        s.add_all(
            [
                ConsultaLog(
                    escritorio_id=e1, modulo="modulo01", servico=SERVICO_CNPJ,
                    operacao="enriquecimento", quantidade=1, creditos_consumidos=2, custo_centavos=5,
                ),
                ConsultaLog(
                    escritorio_id=e2, modulo="modulo01", servico=SERVICO_CNPJ,
                    operacao="enriquecimento", quantidade=1, creditos_consumidos=2, custo_centavos=5,
                ),
            ]
        )
        # Cache GLOBAL de CNPJ + sócios (também é apagado no reset).
        s.add_all(
            [
                Fornecedor(cnpj="11111111111111", razao_social="A", nome_normalizado="A"),
                Fornecedor(cnpj="22222222222222", razao_social="B", nome_normalizado="B"),
            ]
        )
        s.add_all(
            [
                FornecedorSocio(cnpj="11111111111111", nome="Socio Um"),
                FornecedorSocio(cnpj="22222222222222", nome="Socio Dois"),
            ]
        )
        # M02: monitorado + filhos (historico_cnd e alertas referenciam por fornecedor_id).
        mon = FornecedorMonitorado(id=_id(), escritorio_id=e1, cnpj="11111111111111")
        s.add(mon)
        s.add(Alerta(id=_id(), escritorio_id=e1, fornecedor_id=mon.id, tipo="SCORE_CRITICO", mensagem="m"))
        s.add(HistoricoCnd(id=_id(), fornecedor_id=mon.id, escritorio_id=e1, status="NEGATIVA"))
        await s.commit()
    return e1, e2


async def test_reset_apaga_dados_e_preserva_contas_e_login(factory, auth_on):
    e1, e2 = await _semear_dados(factory)
    await _seed_admin(factory)
    # Job em memória que deve sumir após o reset.
    job_store.criar({"status": "concluido"})
    client = TestClient(app)
    token = _login(client, "root@lumen.com", "rootsenha123")

    resp = client.post(
        "/api/admin/reset-ambiente",
        headers=_bearer(token),
        json={"confirmar": "APAGAR TUDO"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "resetado"
    ap = body["apagados"]
    assert ap["analises"] == 2
    assert ap["fornecedores"] == 2
    assert ap["fornecedor_socios"] == 2
    assert ap["escritorio_fornecedor"] == 2
    assert ap["enriquecimento_tentativa"] == 2
    assert ap["consulta_logs"] == 2
    assert ap["monitorados"] == 1
    assert ap["alertas"] == 1
    assert ap["historico_cnd"] == 1

    async with factory() as s:
        # Todas as tabelas de dados ficaram vazias.
        for model in (
            Analise, Fornecedor, FornecedorSocio, EscritorioFornecedor,
            EnriquecimentoTentativa, ConsultaLog, FornecedorMonitorado, Alerta, HistoricoCnd,
        ):
            pk = list(model.__table__.primary_key.columns)[0]
            assert await s.scalar(select(func.count(pk))) == 0

        # Contas e escritórios permanecem (admin + os dois semeados).
        assert await s.get(Escritorio, e1) is not None
        assert await s.get(Escritorio, e2) is not None
        assert await s.scalar(select(func.count(Usuario.id)).where(Usuario.role == ROLE_ADMIN)) == 1

    # Jobs em memória limpos.
    assert job_store.limpar_tudo() == 0

    # Login do admin segue funcionando depois do reset.
    login = client.post("/api/auth/login", json={"email": "root@lumen.com", "senha": "rootsenha123"})
    assert login.status_code == 200
    assert login.json()["access_token"]


async def test_reset_confirmacao_errada_nao_apaga_nada(factory, auth_on):
    e1, e2 = await _semear_dados(factory)
    await _seed_admin(factory)
    client = TestClient(app)
    token = _login(client, "root@lumen.com", "rootsenha123")

    resp = client.post(
        "/api/admin/reset-ambiente",
        headers=_bearer(token),
        json={"confirmar": "apagar tudo"},  # texto não exato
    )
    assert resp.status_code == 400

    async with factory() as s:
        # Nada foi apagado.
        assert await s.scalar(select(func.count(Analise.id))) == 2
        assert await s.scalar(select(func.count(Fornecedor.id))) == 2
        assert await s.scalar(select(func.count(ConsultaLog.id))) == 2
        assert await s.scalar(select(func.count(FornecedorMonitorado.id))) == 1


async def test_reset_403_para_nao_admin(factory, auth_on):
    await _semear_dados(factory)
    client = TestClient(app)
    token = client.post(
        "/api/auth/signup",
        json={"nome_escritorio": "Comum", "email": "comum-reset@a.com", "senha": "senha12345"},
    ).json()["token"]["access_token"]

    resp = client.post(
        "/api/admin/reset-ambiente",
        headers=_bearer(token),
        json={"confirmar": "APAGAR TUDO"},
    )
    assert resp.status_code == 403

    # Garante que nada foi apagado pelo não-admin.
    async with factory() as s:
        assert await s.scalar(select(func.count(Analise.id))) == 2


def test_reset_403_com_auth_off(factory, auth_off):
    client = TestClient(app)
    resp = client.post("/api/admin/reset-ambiente", json={"confirmar": "APAGAR TUDO"})
    assert resp.status_code == 403
