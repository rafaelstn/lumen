"""Geração do relatório PDF via WeasyPrint + Jinja2. Fase 5.

Imports de Jinja2/WeasyPrint são lazy (dentro das funções) para que o módulo possa
ser importado em ambientes sem WeasyPrint (ex.: rodar a suíte no host Windows).
"""
import os
import re
from datetime import datetime

# pdf_generator.py está em app/modules/modulo01/ — sobe dois níveis até app/ e entra em templates/.
_HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(_HERE)), "templates")


def _moeda(valor) -> str:
    try:
        v = float(valor)
    except (TypeError, ValueError):
        v = 0.0
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(valor) -> str:
    try:
        v = float(valor)
    except (TypeError, ValueError):
        v = 0.0
    return f"{v:.2f}".replace(".", ",") + "%"


def _cnpj(valor) -> str:
    """Formata CNPJ (14 dígitos) como 00.000.000/0000-00; sem 14 dígitos, devolve '—'."""
    so = re.sub(r"\D", "", str(valor or ""))
    if len(so) != 14:
        return str(valor) if valor else "—"
    return f"{so[:2]}.{so[2:5]}.{so[5:8]}/{so[8:12]}-{so[12:]}"


_CND_LABEL = {
    "NEGATIVA": "Negativa (regular)",
    "POSITIVA_EFEITO_NEGATIVA": "Positiva c/ efeito de negativa (regular)",
    "POSITIVA": "Positiva (com débitos)",
    "FALHA": "Falha na consulta",
}


def _cnd_label(status) -> str:
    return _CND_LABEL.get(status, status or "—")


def _simnao(valor) -> str:
    if valor is True:
        return "Sim"
    if valor is False:
        return "Não"
    return "—"


def _contexto(job: dict) -> dict:
    from app.modules.modulo01 import risk

    fornecedores = job.get("fornecedores", [])
    verificacao_manual = [
        f
        for f in fornecedores
        if f.get("verificar_st")
        or f.get("cnpj_pendente")
        or (f.get("cnpj") and not f.get("cnpj_confirmado"))
        or f.get("status_cnd") == "FALHA"
    ]
    alertas_risco = risk.alertas_ordenados(fornecedores)
    impacto_total = sum(a.get("impacto_financeiro_anual") or 0 for a in alertas_risco)
    cnd_consultada = any(f.get("status_cnd") for f in fornecedores)
    # Detalhe de CND: só os fornecedores efetivamente consultados (devedores primeiro,
    # depois falhas, depois regulares), para a seção dedicada de regularidade fiscal.
    _ordem_cnd = {"POSITIVA": 0, "FALHA": 1, "POSITIVA_EFEITO_NEGATIVA": 2, "NEGATIVA": 3}
    cnd_detalhes = sorted(
        [f for f in fornecedores if f.get("status_cnd")],
        key=lambda f: _ordem_cnd.get(f.get("status_cnd"), 9),
    )
    return {
        "metadados": job.get("metadados", {}),
        "resumo": job.get("resumo", {}),
        "grupo_a": [f for f in fornecedores if f["grupo"] == "A"],
        "grupo_b": [f for f in fornecedores if f["grupo"] == "B"],
        "grupo_c": [f for f in fornecedores if f["grupo"] == "C"],
        "grupo_indef": [f for f in fornecedores if f["grupo"] == "INDEFINIDO"],
        "verificacao_manual": verificacao_manual,
        "alertas_risco": alertas_risco,
        "impacto_total": impacto_total,
        "cnd_consultada": cnd_consultada,
        "cnd_detalhes": cnd_detalhes,
        "emitido_em": datetime.now().strftime("%d/%m/%Y"),
    }


def _env():
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.filters["moeda"] = _moeda
    env.filters["pct"] = _pct
    env.filters["cnpj"] = _cnpj
    env.filters["cnd_label"] = _cnd_label
    env.filters["simnao"] = _simnao
    return env


def render_html(job: dict) -> str:
    """Renderiza o HTML do relatório (testável sem WeasyPrint)."""
    return _env().get_template("modulo01/relatorio.html").render(**_contexto(job))


def gerar_pdf(job: dict) -> bytes:
    """Renderiza o HTML e converte em PDF via WeasyPrint."""
    from weasyprint import HTML

    html = render_html(job)
    return HTML(string=html, base_url=TEMPLATES_DIR).write_pdf()
