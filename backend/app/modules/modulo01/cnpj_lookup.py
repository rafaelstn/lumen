"""Lookup de CNPJ por razão social e enriquecimento via CNPJá.

Dois usos:
- buscar_por_nome: quando NÃO temos o CNPJ (sem cadastro). Casa a razão social,
  prefere a matriz e exige match exato para confiança alta; caso contrário marca
  como não confirmado (vai para verificação manual no relatório).
- consultar_cnpj: quando JÁ temos o CNPJ. Traz situação cadastral e Simples Nacional
  (valida a classificação A/B/C).

Consome créditos da API. A chave vem só de variável de ambiente, nunca do código.
Toda consulta é registrada (audit trail), sem expor a chave nem dado sensível em claro.
"""
import logging
import re
import unicodedata

import httpx

from app.config import settings

logger = logging.getLogger("modulo01.cnpj_lookup")

# Confiança do match nome → CNPJ.
CONF_ALTA = "alta"          # match exato de razão social, 1 empresa
CONF_BAIXA = "baixa"        # 1 empresa achada, mas sem match exato
CONF_AMBIGUO = "ambiguo"    # várias empresas distintas
CONF_NAO_ENCONTRADO = "nao_encontrado"


class LookupError(Exception):
    """Erro de lookup com mensagem legível (créditos, auth, rede)."""


def validar_cnpj(cnpj: str) -> bool:
    """Valida um CNPJ pelos dígitos verificadores (rejeita entrada manual errada)."""
    c = re.sub(r"\D", "", cnpj or "")
    if len(c) != 14 or len(set(c)) == 1:
        return False

    def _dv(base: str, pesos: list[int]) -> str:
        soma = sum(int(d) * p for d, p in zip(base, pesos))
        resto = soma % 11
        return "0" if resto < 2 else str(11 - resto)

    dv1 = _dv(c[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    dv2 = _dv(c[:13], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return c[12] == dv1 and c[13] == dv2


def _normalizar(nome: str) -> str:
    """Uppercase, sem acentos, sem pontuação, espaços colapsados — para comparar nomes."""
    if not nome:
        return ""
    txt = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    txt = re.sub(r"[^A-Za-z0-9 ]", " ", txt)
    return re.sub(r"\s+", " ", txt).strip().upper()


def melhor_match(nome_alvo: str, records: list[dict]) -> dict:
    """Escolhe o CNPJ a partir dos estabelecimentos retornados (função pura, testável).

    Regras:
    - match exato de razão social (normalizada): confiança alta.
    - 1 empresa (raiz) só, sem exato: confiança baixa.
    - várias empresas distintas: ambíguo (não confirmado).
    """
    alvo = _normalizar(nome_alvo)
    matrizes = [r for r in records if r.get("head")] or records

    exatos = [r for r in matrizes if _normalizar(r.get("company", {}).get("name", "")) == alvo]
    raizes = {r["taxId"][:8] for r in matrizes if r.get("taxId")}

    if len(exatos) == 1:
        r = exatos[0]
        return {
            "cnpj": r["taxId"],
            "nome_oficial": r["company"]["name"],
            "confianca": CONF_ALTA,
            "n_candidatos": len(matrizes),
        }
    if len(raizes) == 1 and matrizes:
        r = matrizes[0]
        return {
            "cnpj": r["taxId"],
            "nome_oficial": r["company"]["name"],
            "confianca": CONF_BAIXA,
            "n_candidatos": len(matrizes),
        }
    if not matrizes:
        return {"cnpj": None, "nome_oficial": None, "confianca": CONF_NAO_ENCONTRADO, "n_candidatos": 0}
    return {"cnpj": None, "nome_oficial": None, "confianca": CONF_AMBIGUO, "n_candidatos": len(matrizes)}


def _headers() -> dict:
    if not settings.cnpj_lookup_api_key:
        raise LookupError("CNPJ_LOOKUP_API_KEY não configurada.")
    return {"Authorization": settings.cnpj_lookup_api_key}


async def buscar_por_nome(nome: str, uf: str | None, client: httpx.AsyncClient) -> dict:
    """Busca CNPJ pela razão social (matrizes), com desambiguação. Consome créditos."""
    params = {"company.name.in": nome, "head.eq": "true", "limit": "10"}
    if uf:
        params["address.state.in"] = uf
    try:
        resp = await client.get(
            f"{settings.cnpj_lookup_base_url}/office", params=params, headers=_headers(), timeout=30
        )
    except httpx.HTTPError as exc:
        raise LookupError(f"Falha de rede na consulta de CNPJ: {exc}") from exc

    if resp.status_code == 401:
        raise LookupError("Chave de API do CNPJá inválida.")
    if resp.status_code == 429:
        raise LookupError("Limite/créditos do CNPJá esgotados.")
    if resp.status_code >= 400:
        raise LookupError(f"Erro {resp.status_code} na consulta de CNPJ.")

    records = resp.json().get("records", [])
    resultado = melhor_match(nome, records)
    logger.info(
        "cnpj_lookup nome=%r uf=%s -> confianca=%s candidatos=%s",
        nome, uf, resultado["confianca"], resultado["n_candidatos"],
    )
    return resultado


async def consultar_cnpj(cnpj: str, client: httpx.AsyncClient) -> dict:
    """Consulta dados do CNPJ (situação cadastral + Simples Nacional). Usa cache p/ economizar."""
    so_digitos = re.sub(r"\D", "", cnpj)
    params = {"simples": "true", "strategy": "CACHE_IF_FRESH", "maxAge": "30"}
    try:
        resp = await client.get(
            f"{settings.cnpj_lookup_base_url}/office/{so_digitos}",
            params=params, headers=_headers(), timeout=30,
        )
    except httpx.HTTPError as exc:
        raise LookupError(f"Falha de rede na consulta de CNPJ: {exc}") from exc

    if resp.status_code == 404:
        return {"cnpj": so_digitos, "encontrado": False}
    if resp.status_code == 429:
        raise LookupError("Limite/créditos do CNPJá esgotados.")
    if resp.status_code >= 400:
        raise LookupError(f"Erro {resp.status_code} na consulta de CNPJ.")

    d = resp.json()
    status = d.get("status", {})
    simples = d.get("company", {}).get("simples", {})
    logger.info("cnpj_lookup consulta cnpj=%s situacao=%s", so_digitos, status.get("text"))
    return {
        "cnpj": so_digitos,
        "encontrado": True,
        "nome_oficial": d.get("company", {}).get("name"),
        "situacao_cadastral": status.get("text"),
        "simples_optante": simples.get("optant"),
    }
