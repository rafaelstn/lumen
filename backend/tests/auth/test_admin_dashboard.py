"""Dashboard admin (/api/admin): resumo, escritórios com agregações, consumo por escritório.

Monta 2 escritórios com consumos diferentes e confere os totais, a separação por escritório
e a integridade do custo em centavos (sem perda). Cobre 403 para não-admin e auth_off.
"""
import uuid

from fastapi.testclient import TestClient

from app.auth import service
from app.main import app
from app.models.analise import Analise
from app.models.escritorio import Escritorio
from app.models.fornecedor import EscritorioFornecedor, Fornecedor
from app.modules.consumo.models import SERVICO_CND, SERVICO_CNPJ, ConsultaLog


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _login(client, email, senha):
    return client.post(
        "/api/auth/login", json={"email": email, "senha": senha}
    ).json()["access_token"]


def _id() -> str:
    return str(uuid.uuid4())


async def _semear_dados(factory):
    """2 escritórios (A, B) com consumos diferentes + análises, fornecedores e cache global.

    A: 1000 créditos CNPJ (custo 2499) + 3 CND (custo 78) = 2577 centavos.
    B: 500 créditos CNPJ (custo 1250) = 1250 centavos.
    """
    esc_a, esc_b = _id(), _id()
    async with factory() as s:
        s.add_all(
            [
                Escritorio(id=esc_a, nome="Escritorio A"),
                Escritorio(id=esc_b, nome="Escritorio B"),
            ]
        )
        # Análises (A: 2, B: 1).
        s.add_all(
            [
                Analise(id=_id(), escritorio_id=esc_a, dados={}, total_fornecedores=0),
                Analise(id=_id(), escritorio_id=esc_a, dados={}, total_fornecedores=0),
                Analise(id=_id(), escritorio_id=esc_b, dados={}, total_fornecedores=0),
            ]
        )
        # Fornecedores pesquisados por escritório (A: 2, B: 1).
        s.add_all(
            [
                EscritorioFornecedor(escritorio_id=esc_a, cnpj="11111111111111"),
                EscritorioFornecedor(escritorio_id=esc_a, cnpj="22222222222222"),
                EscritorioFornecedor(escritorio_id=esc_b, cnpj="33333333333333"),
            ]
        )
        # Cache global: 3 CNPJs, 2 com cadastro completo (cadastro_atualizado_em).
        from datetime import datetime, timezone

        agora = datetime.now(timezone.utc)
        s.add_all(
            [
                Fornecedor(
                    cnpj="11111111111111", razao_social="A", nome_normalizado="A",
                    cadastro_atualizado_em=agora,
                ),
                Fornecedor(
                    cnpj="22222222222222", razao_social="B", nome_normalizado="B",
                    cadastro_atualizado_em=agora,
                ),
                Fornecedor(cnpj="33333333333333", razao_social="C", nome_normalizado="C"),
            ]
        )
        # Audit trail de consumo. custo_centavos é a fonte de verdade.
        s.add_all(
            [
                ConsultaLog(
                    escritorio_id=esc_a, modulo="modulo01", servico=SERVICO_CNPJ,
                    operacao="enriquecimento", quantidade=500, creditos_consumidos=1000,
                    preco_unitario_centavos=2, custo_centavos=2499, consumo_estimado=True,
                ),
                ConsultaLog(
                    escritorio_id=esc_a, modulo="modulo01", servico=SERVICO_CND,
                    operacao="cnd_lote", quantidade=3, creditos_consumidos=3,
                    preco_unitario_centavos=26, custo_centavos=78, consumo_estimado=True,
                ),
                ConsultaLog(
                    escritorio_id=esc_b, modulo="modulo01", servico=SERVICO_CNPJ,
                    operacao="enriquecimento", quantidade=250, creditos_consumidos=500,
                    preco_unitario_centavos=2, custo_centavos=1250, consumo_estimado=True,
                ),
                # Falha sem custo: não conta como consulta paga.
                ConsultaLog(
                    escritorio_id=esc_b, modulo="modulo01", servico=SERVICO_CND,
                    operacao="cnd_lote", quantidade=0, creditos_consumidos=0,
                    preco_unitario_centavos=26, custo_centavos=0, consumo_estimado=True,
                ),
            ]
        )
        await s.commit()

    async with factory() as s:
        await service.seed_admin(s, "root@lumen.com", "rootsenha123")
    return esc_a, esc_b


async def test_resumo_agregacoes_corretas(factory, auth_on):
    await _semear_dados(factory)
    client = TestClient(app)
    token = _login(client, "root@lumen.com", "rootsenha123")

    resp = client.get("/api/admin/resumo", headers=_bearer(token))
    assert resp.status_code == 200
    body = resp.json()

    # 2 escritórios semeados + "Administração" do seed_admin.
    assert body["total_escritorios"] == 3
    assert body["total_usuarios"] == 1  # só o admin tem usuário
    assert body["total_analises"] == 3
    assert body["fornecedores_cache_global"] == 3
    assert body["fornecedores_cadastro_completo"] == 2
    # 3 consultas com custo > 0 (a CND falha de B não conta).
    assert body["consultas_pagas"] == 3
    assert body["creditos_consumidos"] == 1000 + 3 + 500
    # Custo total em centavos, sem perda: 2499 + 78 + 1250.
    assert body["custo_total_centavos"] == 3827
    # Período corrente (mês) cobre tudo recém-inserido.
    assert body["consumo_periodo"]["custo_centavos"] == 3827
    assert body["consumo_periodo"]["inicio"] is not None


async def test_escritorios_com_metricas_e_ordenacao(factory, auth_on):
    esc_a, esc_b = await _semear_dados(factory)
    client = TestClient(app)
    token = _login(client, "root@lumen.com", "rootsenha123")

    resp = client.get("/api/admin/escritorios", headers=_bearer(token))
    assert resp.status_code == 200
    itens = {e["id"]: e for e in resp.json()}

    a = itens[esc_a]
    assert a["total_usuarios"] == 0
    assert a["total_analises"] == 2
    assert a["total_fornecedores_pesquisados"] == 2
    assert a["consumo"]["creditos_consumidos"] == 1003
    assert a["consumo"]["custo_centavos"] == 2577
    assert a["ultima_atividade"] is not None

    b = itens[esc_b]
    assert b["total_analises"] == 1
    assert b["consumo"]["custo_centavos"] == 1250

    # Ordenação por custo desc: A (2577) antes de B (1250); "Administração" (0) por último.
    ordem = [e["id"] for e in resp.json()]
    assert ordem.index(esc_a) < ordem.index(esc_b)


async def test_consumo_por_escritorio_quebra_por_servico(factory, auth_on):
    esc_a, esc_b = await _semear_dados(factory)
    client = TestClient(app)
    token = _login(client, "root@lumen.com", "rootsenha123")

    resp = client.get("/api/admin/consumo-por-escritorio", headers=_bearer(token))
    assert resp.status_code == 200
    itens = {e["escritorio_id"]: e for e in resp.json()}

    # Só escritórios com consumo aparecem (A e B; Administração não consumiu).
    assert set(itens) == {esc_a, esc_b}
    a = itens[esc_a]
    assert a["custo_centavos"] == 2577
    assert a["por_servico"]["cnpj"]["custo_centavos"] == 2499
    assert a["por_servico"]["cnd"]["custo_centavos"] == 78
    assert a["por_servico"]["cnd"]["creditos_consumidos"] == 3

    b = itens[esc_b]
    assert b["por_servico"]["cnpj"]["custo_centavos"] == 1250
    # CND de B foi 0 crédito (falha): não vira consulta paga, mas pode aparecer com custo 0.
    assert b["por_servico"].get("cnd", {"custo_centavos": 0})["custo_centavos"] == 0


async def test_detalhe_escritorio(factory, auth_on):
    esc_a, _ = await _semear_dados(factory)
    client = TestClient(app)
    token = _login(client, "root@lumen.com", "rootsenha123")

    resp = client.get(f"/api/admin/escritorio/{esc_a}", headers=_bearer(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["nome"] == "Escritorio A"
    assert body["total_analises"] == 2
    assert body["total_fornecedores_pesquisados"] == 2
    assert body["consumo"]["custo_centavos"] == 2577
    assert body["consumo"]["por_servico"]["cnpj"]["custo_centavos"] == 2499


async def test_detalhe_escritorio_inexistente_404(factory, auth_on):
    async with factory() as s:
        await service.seed_admin(s, "root@lumen.com", "rootsenha123")
    client = TestClient(app)
    token = _login(client, "root@lumen.com", "rootsenha123")
    resp = client.get("/api/admin/escritorio/nao-existe", headers=_bearer(token))
    assert resp.status_code == 404


def test_resumo_403_para_nao_admin(factory, auth_on):
    client = TestClient(app)
    token = client.post(
        "/api/auth/signup",
        json={"nome_escritorio": "Comum", "email": "comum2@a.com", "senha": "senha12345"},
    ).json()["token"]["access_token"]
    assert client.get("/api/admin/resumo", headers=_bearer(token)).status_code == 403
    assert (
        client.get("/api/admin/consumo-por-escritorio", headers=_bearer(token)).status_code
        == 403
    )


def test_resumo_403_com_auth_off(factory, auth_off):
    client = TestClient(app)
    assert client.get("/api/admin/resumo").status_code == 403
    assert client.get("/api/admin/consumo-por-escritorio").status_code == 403
