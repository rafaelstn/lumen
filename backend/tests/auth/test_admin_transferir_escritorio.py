"""Transferência admin de dados entre escritórios (POST /api/admin/escritorios/transferir).

Caso de uso: o admin gerou dados no escritório default (modo anônimo, antes do login) e
quer consolidá-los no escritório dele. Cobre: reatribuição de todos os dados de tenant de
ORIGEM para DESTINO (origem fica vazia, destino recebe); tratamento de conflito de UNIQUE
(escritorio_fornecedor por CNPJ; o registro da origem é descartado, não duplica nem viola
a constraint); preservação do cache global de fornecedores; e os contratos de erro
(403 não-admin, 400 origem==destino, 404 inexistente).
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
)
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


async def _seed_dois_escritorios(factory):
    """Origem A e destino B vazios (só os registros de Escritorio). Devolve (a, b)."""
    a, b = _id(), _id()
    async with factory() as s:
        s.add_all([Escritorio(id=a, nome="Origem"), Escritorio(id=b, nome="Destino")])
        await s.commit()
    return a, b


# --- Transferência feliz ------------------------------------------------------------


async def test_transfere_dados_de_a_para_b_origem_fica_vazia(factory, auth_on):
    a, b = await _seed_dois_escritorios(factory)
    async with factory() as s:
        # Dados de tenant na ORIGEM (A), sem nenhum conflito com B (que está vazio).
        s.add(Analise(id=_id(), escritorio_id=a, dados={}))
        s.add(EscritorioFornecedor(escritorio_id=a, cnpj="11111111111111"))
        s.add(
            EnriquecimentoTentativa(
                escritorio_id=a, nome_normalizado="ACME", resultado="nao_encontrado"
            )
        )
        s.add(
            ConsultaLog(
                escritorio_id=a, modulo="modulo01", servico=SERVICO_CNPJ,
                operacao="enriquecimento", quantidade=1, creditos_consumidos=2, custo_centavos=5,
            )
        )
        mon = FornecedorMonitorado(id=_id(), escritorio_id=a, cnpj="11111111111111")
        s.add(mon)
        s.add(Alerta(id=_id(), escritorio_id=a, fornecedor_id=mon.id, tipo="SCORE_CRITICO", mensagem="m"))
        s.add(HistoricoCnd(id=_id(), fornecedor_id=mon.id, escritorio_id=a, status="NEGATIVA"))
        await s.commit()

    await _seed_admin(factory)
    client = TestClient(app)
    token = _login(client, "root@lumen.com", "rootsenha123")

    resp = client.post(
        "/api/admin/escritorios/transferir",
        headers=_bearer(token),
        json={"origem_id": a, "destino_id": b},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["origem_id"] == a
    assert body["destino_id"] == b
    assert body["status"] == "transferido"
    mov = body["movidos"]
    assert mov["analises"] == 1
    assert mov["escritorio_fornecedor"] == 1
    assert mov["enriquecimento_tentativa"] == 1
    assert mov["consulta_logs"] == 1
    assert mov["fornecedores_monitorados"] == 1
    assert mov["alertas"] == 1
    assert mov["historico_cnd"] == 1
    assert mov["conflitos_descartados"] == 0

    async with factory() as s:
        # A (origem) fica vazia em todas as tabelas de tenant.
        for model, col in (
            (Analise, Analise.escritorio_id),
            (EscritorioFornecedor, EscritorioFornecedor.escritorio_id),
            (EnriquecimentoTentativa, EnriquecimentoTentativa.escritorio_id),
            (ConsultaLog, ConsultaLog.escritorio_id),
            (FornecedorMonitorado, FornecedorMonitorado.escritorio_id),
            (Alerta, Alerta.escritorio_id),
            (HistoricoCnd, HistoricoCnd.escritorio_id),
        ):
            assert await s.scalar(select(func.count()).select_from(model).where(col == a)) == 0
            assert await s.scalar(select(func.count()).select_from(model).where(col == b)) == 1
        # Os dois escritórios continuam existindo (transferência não apaga escritório).
        assert await s.get(Escritorio, a) is not None
        assert await s.get(Escritorio, b) is not None


# --- Conflito de UNIQUE: escritorio_fornecedor (mesmo CNPJ nos dois) -----------------


async def test_conflito_escritorio_fornecedor_nao_duplica_descarta_origem(factory, auth_on):
    a, b = await _seed_dois_escritorios(factory)
    async with factory() as s:
        # Mesmo CNPJ associado em A e B: B já vê, A é descartado (não viola unique).
        s.add(EscritorioFornecedor(escritorio_id=a, cnpj="22222222222222"))
        s.add(EscritorioFornecedor(escritorio_id=b, cnpj="22222222222222"))
        # CNPJ exclusivo de A: esse migra normalmente.
        s.add(EscritorioFornecedor(escritorio_id=a, cnpj="33333333333333"))
        # Conflito também em enriquecimento_tentativa (mesmo nome_normalizado).
        s.add(EnriquecimentoTentativa(escritorio_id=a, nome_normalizado="DUP", resultado="ambiguo"))
        s.add(EnriquecimentoTentativa(escritorio_id=b, nome_normalizado="DUP", resultado="nao_encontrado"))
        await s.commit()

    await _seed_admin(factory)
    client = TestClient(app)
    token = _login(client, "root@lumen.com", "rootsenha123")

    resp = client.post(
        "/api/admin/escritorios/transferir",
        headers=_bearer(token),
        json={"origem_id": a, "destino_id": b},
    )
    assert resp.status_code == 200
    mov = resp.json()["movidos"]
    assert mov["escritorio_fornecedor"] == 1  # só o CNPJ exclusivo de A migrou.
    assert mov["enriquecimento_tentativa"] == 0  # o único de A colidia com B.
    assert mov["conflitos_descartados"] == 2  # 1 assoc + 1 tentativa descartadas.

    async with factory() as s:
        # B tem o CNPJ conflitante UMA vez (não duplicou) + o exclusivo de A.
        cnpjs_b = set(
            (
                await s.execute(
                    select(EscritorioFornecedor.cnpj).where(EscritorioFornecedor.escritorio_id == b)
                )
            ).scalars()
        )
        assert cnpjs_b == {"22222222222222", "33333333333333"}
        assert await s.scalar(
            select(func.count())
            .select_from(EscritorioFornecedor)
            .where(EscritorioFornecedor.escritorio_id == b, EscritorioFornecedor.cnpj == "22222222222222")
        ) == 1
        # A ficou sem associações.
        assert await s.scalar(
            select(func.count()).select_from(EscritorioFornecedor).where(EscritorioFornecedor.escritorio_id == a)
        ) == 0
        # Tentativa: B mantém só a sua (não duplica o nome DUP).
        assert await s.scalar(
            select(func.count())
            .select_from(EnriquecimentoTentativa)
            .where(EnriquecimentoTentativa.escritorio_id == b, EnriquecimentoTentativa.nome_normalizado == "DUP")
        ) == 1


async def test_conflito_monitorado_reaponta_historico_e_alerta_para_destino(factory, auth_on):
    a, b = await _seed_dois_escritorios(factory)
    async with factory() as s:
        # Mesmo CNPJ monitorado em A e B. O monitorado de A é descartado; seus filhos
        # (historico/alerta) são reapontados para o monitorado de B.
        mon_b = FornecedorMonitorado(id=_id(), escritorio_id=b, cnpj="44444444444444")
        mon_a = FornecedorMonitorado(id=_id(), escritorio_id=a, cnpj="44444444444444")
        s.add_all([mon_b, mon_a])
        s.add(Alerta(id=_id(), escritorio_id=a, fornecedor_id=mon_a.id, tipo="SCORE_CRITICO", mensagem="m"))
        s.add(HistoricoCnd(id=_id(), fornecedor_id=mon_a.id, escritorio_id=a, status="NEGATIVA"))
        await s.commit()
        mon_b_id = mon_b.id

    await _seed_admin(factory)
    client = TestClient(app)
    token = _login(client, "root@lumen.com", "rootsenha123")

    resp = client.post(
        "/api/admin/escritorios/transferir",
        headers=_bearer(token),
        json={"origem_id": a, "destino_id": b},
    )
    assert resp.status_code == 200
    mov = resp.json()["movidos"]
    assert mov["fornecedores_monitorados"] == 0  # o único de A colidia com B.
    assert mov["conflitos_descartados"] == 1
    assert mov["alertas"] == 1
    assert mov["historico_cnd"] == 1

    async with factory() as s:
        # B mantém UM só monitorado para o CNPJ (sem duplicar).
        assert await s.scalar(
            select(func.count())
            .select_from(FornecedorMonitorado)
            .where(FornecedorMonitorado.escritorio_id == b, FornecedorMonitorado.cnpj == "44444444444444")
        ) == 1
        # Os filhos migraram para B e apontam para o monitorado de B.
        alerta = (await s.execute(select(Alerta).where(Alerta.escritorio_id == b))).scalar_one()
        hist = (await s.execute(select(HistoricoCnd).where(HistoricoCnd.escritorio_id == b))).scalar_one()
        assert alerta.fornecedor_id == mon_b_id
        assert hist.fornecedor_id == mon_b_id
        # A ficou sem monitorados.
        assert await s.scalar(
            select(func.count()).select_from(FornecedorMonitorado).where(FornecedorMonitorado.escritorio_id == a)
        ) == 0


async def test_transferencia_preserva_cache_global_de_fornecedor(factory, auth_on):
    a, b = await _seed_dois_escritorios(factory)
    async with factory() as s:
        s.add(EscritorioFornecedor(escritorio_id=a, cnpj="55555555555555"))
        # Cache GLOBAL: 1 fornecedor que NÃO pode ser tocado pela transferência.
        s.add(Fornecedor(cnpj="55555555555555", razao_social="Global", nome_normalizado="GLOBAL"))
        await s.commit()

    await _seed_admin(factory)
    client = TestClient(app)
    token = _login(client, "root@lumen.com", "rootsenha123")

    resp = client.post(
        "/api/admin/escritorios/transferir",
        headers=_bearer(token),
        json={"origem_id": a, "destino_id": b},
    )
    assert resp.status_code == 200

    async with factory() as s:
        # O cadastro global permanece intacto (1 registro, mesmo CNPJ).
        assert await s.scalar(
            select(func.count()).select_from(Fornecedor).where(Fornecedor.cnpj == "55555555555555")
        ) == 1


# --- Contratos de erro --------------------------------------------------------------


async def test_transferir_403_para_nao_admin(factory, auth_on):
    a, b = await _seed_dois_escritorios(factory)
    client = TestClient(app)
    token = client.post(
        "/api/auth/signup",
        json={"nome_escritorio": "Comum", "email": "comumt@a.com", "senha": "senha12345"},
    ).json()["token"]["access_token"]
    resp = client.post(
        "/api/admin/escritorios/transferir",
        headers=_bearer(token),
        json={"origem_id": a, "destino_id": b},
    )
    assert resp.status_code == 403


def test_transferir_403_com_auth_off(factory, auth_off):
    client = TestClient(app)
    resp = client.post(
        "/api/admin/escritorios/transferir",
        json={"origem_id": "a", "destino_id": "b"},
    )
    assert resp.status_code == 403


async def test_transferir_origem_igual_destino_400(factory, auth_on):
    a, _ = await _seed_dois_escritorios(factory)
    await _seed_admin(factory)
    client = TestClient(app)
    token = _login(client, "root@lumen.com", "rootsenha123")
    resp = client.post(
        "/api/admin/escritorios/transferir",
        headers=_bearer(token),
        json={"origem_id": a, "destino_id": a},
    )
    assert resp.status_code == 400


async def test_transferir_origem_inexistente_404(factory, auth_on):
    _, b = await _seed_dois_escritorios(factory)
    await _seed_admin(factory)
    client = TestClient(app)
    token = _login(client, "root@lumen.com", "rootsenha123")
    resp = client.post(
        "/api/admin/escritorios/transferir",
        headers=_bearer(token),
        json={"origem_id": "nao-existe", "destino_id": b},
    )
    assert resp.status_code == 404


async def test_transferir_destino_inexistente_404(factory, auth_on):
    a, _ = await _seed_dois_escritorios(factory)
    await _seed_admin(factory)
    client = TestClient(app)
    token = _login(client, "root@lumen.com", "rootsenha123")
    resp = client.post(
        "/api/admin/escritorios/transferir",
        headers=_bearer(token),
        json={"origem_id": a, "destino_id": "nao-existe"},
    )
    assert resp.status_code == 404
