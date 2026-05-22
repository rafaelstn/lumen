"""Teste da renderização do relatório (HTML via Jinja2; o PDF/WeasyPrint roda no container)."""
from app.modules.modulo01 import pdf_generator, service


def test_render_html_contem_secoes_e_dados(idesan_xls):
    metadados, resumo, fornecedores = service.processar(idesan_xls)
    job = {"metadados": metadados, "resumo": resumo, "fornecedores": fornecedores}
    html = pdf_generator.render_html(job)

    assert "IDESAN COMERCIAL LTDA" in html  # capa com o cliente
    assert "Sumário Executivo" in html
    assert "Grupo A" in html and "Grupo C" in html
    assert "Verificação Manual" in html
    assert "METAL CUT" in html  # caso especial aparece na verificação manual


def test_filtros_de_formatacao():
    assert pdf_generator._moeda(49680.33) == "R$ 49.680,33"
    assert pdf_generator._moeda(0) == "R$ 0,00"
    assert pdf_generator._pct(18) == "18,00%"
