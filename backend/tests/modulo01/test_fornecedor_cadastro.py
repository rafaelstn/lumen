"""Testes do cadastro completo de fornecedor (endereço/contato/atividade/sócios).

Cobre:
- extrair_cadastro normaliza um record do CNPJá /office (mesmo shape da busca por nome e do detalhe).
- salvar_cadastro grava fornecedor + sócios (tabela separada), idempotente (re-gravar não duplica).
- obter_cadastro_completo devolve o cadastro + sócios.
- capital social vai para centavos inteiros (nunca float).
"""

from app.models.fornecedor import Fornecedor, FornecedorSocio
from app.modules.modulo01 import cnpj_lookup, fornecedores_repo

CNPJ = "37335118000180"

# Record no shape do CNPJá /office (busca por nome E detalhe devolvem este objeto completo).
RECORD = {
    "taxId": "37.335.118/0001-80",
    "alias": "ACME COMERCIO",
    "founded": "2010-03-15",
    "company": {
        "name": "ACME INDUSTRIA E COMERCIO LTDA",
        "equity": 150000.50,
        "nature": {"text": "Sociedade Empresária Limitada"},
        "size": {"text": "DEMAIS"},
        "members": [
            {"person": {"name": "JOAO DA SILVA"}, "role": {"text": "Sócio-Administrador"}, "since": "2010-03-15"},
            {"person": {"name": "MARIA SOUZA"}, "role": {"text": "Sócia"}, "since": "2012-06-01"},
        ],
    },
    "address": {
        "street": "RUA DAS FLORES", "number": "100", "details": "SALA 2",
        "district": "CENTRO", "city": "SAO PAULO", "state": "SP", "zip": "01001-000",
    },
    "phones": [{"area": "11", "number": "3333-4444"}, {"area": "11", "number": "99999-8888"}],
    "emails": [{"address": "contato@acme.com"}, {"address": "fiscal@acme.com"}],
    "mainActivity": {"id": "4711301", "text": "Comércio varejista"},
    "sideActivities": [{"id": "4712100", "text": "Minimercados"}],
    "status": {"text": "Ativa"},
}


def test_extrair_cadastro_normaliza_record_completo():
    c = cnpj_lookup.extrair_cadastro(RECORD)
    assert c["cnpj"] == CNPJ  # só dígitos
    assert c["razao_social"] == "ACME INDUSTRIA E COMERCIO LTDA"
    assert c["nome_fantasia"] == "ACME COMERCIO"
    assert c["logradouro"] == "RUA DAS FLORES"
    assert c["numero"] == "100"
    assert c["municipio"] == "SAO PAULO"
    assert c["uf"] == "SP"
    assert c["cep"] == "01001000"
    assert c["telefone_principal"] == "1133334444"
    assert c["email_principal"] == "contato@acme.com"
    assert c["contatos"]["telefones"] == ["1133334444", "11999998888"]
    assert c["contatos"]["emails"] == ["contato@acme.com", "fiscal@acme.com"]
    assert c["cnae_principal_codigo"] == "4711301"
    assert c["cnaes_secundarios"] == [{"codigo": "4712100", "descricao": "Minimercados"}]
    assert c["porte"] == "DEMAIS"
    assert c["natureza_juridica"] == "Sociedade Empresária Limitada"
    assert c["situacao_cadastral"] == "Ativa"
    assert c["data_abertura"] == "2010-03-15"
    # Dinheiro em centavos inteiros, nunca float: 150000.50 -> 15000050.
    assert c["capital_social_centavos"] == 15000050
    assert isinstance(c["capital_social_centavos"], int)
    assert len(c["socios"]) == 2
    assert c["socios"][0] == {"nome": "JOAO DA SILVA", "qualificacao": "Sócio-Administrador", "desde": "2010-03-15"}


def test_extrair_cadastro_tolera_record_vazio():
    c = cnpj_lookup.extrair_cadastro({})
    assert c["cnpj"] == ""
    assert c["razao_social"] is None
    assert c["socios"] == []
    assert c["contatos"] is None
    assert c["capital_social_centavos"] is None


async def test_salvar_cadastro_grava_fornecedor_e_socios_separados(session):
    cadastro = cnpj_lookup.extrair_cadastro(RECORD)
    await fornecedores_repo.salvar_cadastro(session, cadastro, "cnpja")

    forn = await fornecedores_repo._fornecedor_por_cnpj(session, CNPJ)
    assert forn is not None
    assert forn.razao_social == "ACME INDUSTRIA E COMERCIO LTDA"
    assert forn.municipio == "SAO PAULO"
    assert forn.capital_social_centavos == 15000050
    assert forn.origem == "cnpja"
    assert forn.cadastro_atualizado_em is not None

    # Sócios em tabela SEPARADA (LGPD): não são atributo do Fornecedor.
    res = await session.execute(FornecedorSocio.__table__.select())
    socios = res.fetchall()
    assert len(socios) == 2


async def test_salvar_cadastro_idempotente_nao_duplica_socios(session):
    cadastro = cnpj_lookup.extrair_cadastro(RECORD)
    await fornecedores_repo.salvar_cadastro(session, cadastro, "cnpja")
    # Re-grava o mesmo CNPJ: atualiza o fornecedor e SUBSTITUI o conjunto de sócios.
    await fornecedores_repo.salvar_cadastro(session, cadastro, "cnpja")

    res = await session.execute(Fornecedor.__table__.select())
    assert len(res.fetchall()) == 1  # 1 fornecedor, não duplicou
    res = await session.execute(FornecedorSocio.__table__.select())
    assert len(res.fetchall()) == 2  # 2 sócios, não viraram 4


async def test_salvar_cadastro_substitui_quadro_societario(session):
    await fornecedores_repo.salvar_cadastro(session, cnpj_lookup.extrair_cadastro(RECORD), "cnpja")
    # Quadro societário mudou: sai a Maria, entra o Pedro.
    novo = dict(RECORD)
    novo["company"] = dict(RECORD["company"])
    novo["company"]["members"] = [
        {"person": {"name": "JOAO DA SILVA"}, "role": {"text": "Sócio-Administrador"}, "since": "2010-03-15"},
        {"person": {"name": "PEDRO LIMA"}, "role": {"text": "Sócio"}, "since": "2024-01-10"},
    ]
    await fornecedores_repo.salvar_cadastro(session, cnpj_lookup.extrair_cadastro(novo), "cnpja")

    cadastro = await fornecedores_repo.obter_cadastro_completo(session, CNPJ)
    nomes = {s["nome"] for s in cadastro["socios"]}
    assert nomes == {"JOAO DA SILVA", "PEDRO LIMA"}  # Maria saiu, sem duplicar João


async def test_salvar_cadastro_nao_apaga_razao_boa_por_vazio(session):
    await fornecedores_repo.salvar_cadastro(session, cnpj_lookup.extrair_cadastro(RECORD), "cnpja")
    # Retorno parcial sem razão social não deve zerar a razão já gravada.
    parcial = {"cnpj": CNPJ, "razao_social": None, "uf": "RJ", "socios": []}
    await fornecedores_repo.salvar_cadastro(session, parcial, "cnpja")
    forn = await fornecedores_repo._fornecedor_por_cnpj(session, CNPJ)
    assert forn.razao_social == "ACME INDUSTRIA E COMERCIO LTDA"
    assert forn.uf == "RJ"  # mas o campo novo não-vazio atualizou


async def test_obter_cadastro_completo_devolve_tudo_incl_socios(session):
    await fornecedores_repo.salvar_cadastro(session, cnpj_lookup.extrair_cadastro(RECORD), "cnpja")
    c = await fornecedores_repo.obter_cadastro_completo(session, CNPJ)
    assert c["cnpj"] == CNPJ
    assert c["endereco"]["municipio"] == "SAO PAULO"
    assert c["contato"]["email_principal"] == "contato@acme.com"
    assert c["atividade"]["capital_social_centavos"] == 15000050
    assert len(c["socios"]) == 2


async def test_obter_cadastro_inexistente_retorna_none(session):
    assert await fornecedores_repo.obter_cadastro_completo(session, "00000000000000") is None


async def test_salvar_cadastro_sem_cnpj_e_noop(session):
    await fornecedores_repo.salvar_cadastro(session, {"cnpj": "", "razao_social": "X"}, "cnpja")
    res = await session.execute(Fornecedor.__table__.select())
    assert res.fetchall() == []
