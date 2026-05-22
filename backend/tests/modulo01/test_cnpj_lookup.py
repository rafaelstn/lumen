"""Testes da lógica de match nome → CNPJ (puros, sem chamar a API)."""
from app.modules.modulo01 import cnpj_lookup as cl


def _rec(taxId, nome, head=True):
    return {"taxId": taxId, "head": head, "company": {"name": nome}}


def test_normalizar_remove_acento_e_pontuacao():
    assert cl._normalizar("ARCELORMITTAL BRASIL S.A.") == "ARCELORMITTAL BRASIL S A"
    assert cl._normalizar("Comércio & Cia Ltda.") == "COMERCIO CIA LTDA"


def test_match_exato_confianca_alta():
    records = [
        _rec("17469701000177", "ARCELORMITTAL BRASIL S.A."),
        _rec("09266140000180", "ARCELORMITTAL BRASIL SSC PARTICIPACOES S.A"),
    ]
    r = cl.melhor_match("ARCELORMITTAL BRASIL S.A.", records)
    assert r["confianca"] == cl.CONF_ALTA
    assert r["cnpj"] == "17469701000177"


def test_multiplas_empresas_ambiguo():
    records = [
        _rec("17469701000177", "ARCELORMITTAL BRASIL S.A."),
        _rec("09266140000180", "ARCELORMITTAL BRASIL SSC PARTICIPACOES S.A"),
        _rec("02235994000150", "ARCELORMITTAL GONVARRI BRASIL"),
    ]
    r = cl.melhor_match("ARCELORMITTAL", records)
    assert r["confianca"] == cl.CONF_AMBIGUO
    assert r["cnpj"] is None


def test_uma_empresa_sem_exato_confianca_baixa():
    records = [
        _rec("03063350000195", "BORRACHAS MOEMA INDUSTRIA LTDA"),
        _rec("03063350000276", "BORRACHAS MOEMA INDUSTRIA LTDA", head=False),
    ]
    r = cl.melhor_match("BORRACHAS MOEMA LTDA", records)
    assert r["confianca"] == cl.CONF_BAIXA
    assert r["cnpj"] == "03063350000195"  # matriz


def test_nada_encontrado():
    r = cl.melhor_match("EMPRESA INEXISTENTE LTDA", [])
    assert r["confianca"] == cl.CONF_NAO_ENCONTRADO
    assert r["cnpj"] is None


def test_validar_cnpj():
    assert cl.validar_cnpj("37335118000180") is True       # CNPJ real (CNPJá)
    assert cl.validar_cnpj("37.335.118/0001-80") is True    # formatado
    assert cl.validar_cnpj("37335118000181") is False       # DV errado
    assert cl.validar_cnpj("11111111111111") is False       # todos iguais
    assert cl.validar_cnpj("123") is False                  # tamanho errado
