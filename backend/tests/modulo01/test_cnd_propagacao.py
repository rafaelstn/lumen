"""Propagação dos campos completos de CND até o GET /resultado (schema FornecedorResult).

Injeta um job no store com um fornecedor já enriquecido pela CND (sucesso e falha) e confere
que os campos novos chegam intactos na resposta da API. auth desligada: contexto anônimo.
"""
from fastapi.testclient import TestClient

from app.main import app
from app.modules.modulo01.jobs import store


def _fornecedor_base(cod: str, **extra) -> dict:
    base = {
        "cod_forn": cod,
        "nome_forn": f"Fornecedor {cod}",
        "cnpj": "51260859000170",
        "grupo": "A",
        "label": "Grupo A",
        "total_compras": 1000.0,
        "total_valor_icms": 180.0,
        "aliquota_max": 18.0,
        "aliquota_efetiva_pct": 18.0,
        "credito_aproveitado": 180.0,
        "credito_perdido": 0.0,
        "n_lancamentos": 3,
    }
    base.update(extra)
    return base


def _resumo() -> dict:
    return {
        "total_fornecedores": 2,
        "grupo_a": 2,
        "grupo_b": 0,
        "grupo_c": 0,
        "caso_especial": 0,
        "total_credito_aproveitado": 360.0,
        "total_compras_sem_credito": 0.0,
    }


def test_resultado_expoe_campos_cnd_sucesso_e_falha():
    forn_ok = _fornecedor_base(
        "0001",
        status_cnd="NEGATIVA",
        cnd_descricao="",
        cnd_tipo="Certidão Negativa de Débitos relativos a Tributos Federais",
        cnd_certidao_codigo="078A.05F6.FFC6.C668",
        cnd_emissao_data="25/05/2026",
        cnd_validade="21/11/2026",
        cnd_consulta_datahora="25/05/2026 23:18:17",
        cnd_debitos_rfb=False,
        cnd_debitos_pgfn=False,
        cnd_comprovante_url=None,
        cnd_falha_motivo=None,
    )
    forn_falha = _fornecedor_base(
        "0002",
        status_cnd="FALHA",
        cnd_descricao="Tempo de resposta excedido na fonte.",
        cnd_falha_motivo="Tempo de resposta excedido na consulta à Receita/PGFN.",
    )

    job_id = store.criar(
        {
            "status": "parsed",
            "metadados": {"cliente": "Teste"},
            "resumo": _resumo(),
            "fornecedores": [forn_ok, forn_falha],
        }
    )

    client = TestClient(app)
    resp = client.get(f"/api/modulo01/resultado/{job_id}")
    assert resp.status_code == 200
    forns = {f["cod_forn"]: f for f in resp.json()["fornecedores"]}

    ok = forns["0001"]
    assert ok["status_cnd"] == "NEGATIVA"
    assert ok["cnd_certidao_codigo"] == "078A.05F6.FFC6.C668"
    assert ok["cnd_tipo"].startswith("Certidão Negativa")
    assert ok["cnd_emissao_data"] == "25/05/2026"
    assert ok["cnd_validade"] == "21/11/2026"
    assert ok["cnd_consulta_datahora"] == "25/05/2026 23:18:17"
    assert ok["cnd_debitos_rfb"] is False
    assert ok["cnd_debitos_pgfn"] is False
    assert ok["cnd_falha_motivo"] is None

    falha = forns["0002"]
    assert falha["status_cnd"] == "FALHA"
    assert falha["cnd_falha_motivo"] == "Tempo de resposta excedido na consulta à Receita/PGFN."

    store.remover(job_id)
