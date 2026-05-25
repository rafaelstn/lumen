"""Testes do parser, validados contra o arquivo real (idesan.xls)."""
from decimal import Decimal


from app.modules.modulo01 import parser


def test_parse_entradas_filtra_icms_e_cfops(idesan_xls):
    df = parser.parse_entradas(idesan_xls)
    assert not df.empty
    # Só lançamentos de ICMS nos CFOPs de interesse.
    assert set(df["cfop"].unique()).issubset(set(parser.CFOPS_INTERESSE))
    # Valores monetários são Decimal (precisão fiscal).
    assert all(isinstance(v, Decimal) for v in df["valor_icms"])
    assert all(isinstance(v, Decimal) for v in df["valor_contabil"])


def test_merge_agrupa_57_fornecedores(idesan_xls):
    df = parser.parse_entradas(idesan_xls)
    merged = parser.merge_fornecedores(df)
    assert len(merged) == 57
    # Sem cadastro, todo CNPJ fica pendente.
    assert merged["cnpj_pendente"].all()
    assert merged["cnpj"].isna().all()


def test_totais_batem_com_referencia(idesan_xls):
    df = parser.parse_entradas(idesan_xls)
    merged = parser.merge_fornecedores(df)

    grupo_a = merged[merged["aliquota_max"] >= Decimal("12")]
    grupo_c = merged[merged["aliquota_max"] == Decimal("0")]

    credito_a = sum((v for v in grupo_a["total_valor_icms"]), Decimal("0.00"))
    compras_c = sum((v for v in grupo_c["total_compras"]), Decimal("0.00"))

    assert len(grupo_a) == 35
    assert credito_a == Decimal("49315.24")
    assert len(grupo_c) == 15
    assert compras_c == Decimal("62847.62")


def test_money_usa_decimal_e_arredonda_half_up():
    assert parser._money(56.99) == Decimal("56.99")
    assert parser._money("") == Decimal("0.00")
    assert parser._money(None) == Decimal("0.00")
    # ROUND_HALF_UP
    assert parser._money(Decimal("0.125")) == Decimal("0.13")


def test_money_celula_suja_nao_quebra():
    # Texto não-numérico (dado sujo) vira 0.00 em vez de lançar exceção.
    assert parser._rate("ICMS") == Decimal("0.00")
    assert parser._money("abc") == Decimal("0.00")


def test_excel_date_iso_converte_serial():
    # 46126 corresponde a uma data de 2026 no sistema de datas 1900 do Excel.
    iso = parser._excel_date_iso(46126.0)
    assert iso is not None and iso.startswith("2026-")
    assert parser._excel_date_iso("") is None
