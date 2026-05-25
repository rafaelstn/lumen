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
import asyncio
import logging
import re
import time
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
    """Erro de lookup com mensagem legível (crédito real esgotado, auth, rede)."""


class RateLimitError(LookupError):
    """429 por taxa (transitório): o plano tem limite de req/min e batemos o teto.

    NÃO é crédito esgotado. O lote deve parar e o usuário aguardar ~1 min e tentar de novo.
    Subclasse de LookupError para não quebrar quem captura LookupError genérico, mas o
    chamador que distingue rate vs crédito captura RateLimitError primeiro.

    retry_after: segundos sugeridos pela origem (header Retry-After), quando informado.
    """

    def __init__(self, mensagem: str, retry_after: float | None = None) -> None:
        super().__init__(mensagem)
        self.retry_after = retry_after


# Heurística de corpo/headers para distinguir 429 de taxa x crédito real esgotado.
# O 429 do CNPJá por taxa é o caso comum quando a conta TEM saldo; só tratamos como
# crédito esgotado quando o corpo deixa claro (ex.: "credit"/"saldo"/"quota").
_PADRAO_CREDITO_ESGOTADO = re.compile(
    r"cr[eé]dit|saldo|quota|insufficient|exceeded.*plan|limite\s+do\s+plano", re.IGNORECASE
)


def _parse_retry_after(valor: str | None) -> float | None:
    """Lê o header Retry-After (segundos). Ignora formato data (raro nesta API)."""
    if not valor:
        return None
    try:
        segundos = float(valor.strip())
        return segundos if segundos >= 0 else None
    except ValueError:
        return None


def _erro_de_429(resp: httpx.Response) -> LookupError:
    """Classifica um HTTP 429: crédito real esgotado (LookupError) x rate limit (RateLimitError).

    Default é rate limit (transitório), porque com saldo na conta o 429 do plano é quase
    sempre limite de req/min. Só vira crédito esgotado com sinal explícito no corpo.
    """
    corpo = ""
    try:
        corpo = resp.text or ""
    except Exception:  # corpo ilegível: trata como rate limit (caso comum)
        corpo = ""
    if _PADRAO_CREDITO_ESGOTADO.search(corpo):
        return LookupError("Créditos de consulta de CNPJ esgotados.")
    retry_after = _parse_retry_after(resp.headers.get("Retry-After"))
    return RateLimitError("Limite de consultas por minuto atingido (aguarde ~1 min).", retry_after)


class _Throttle:
    """Espaça chamadas para não passar de N por minuto. Compartilhado por um lote.

    Calcula o intervalo mínimo entre chamadas (60/rate, com folga) e dorme o tempo restante
    antes de liberar a próxima. Monotônico (time.monotonic), imune a ajuste de relógio.
    """

    def __init__(self, rate_por_min: int, folga: float = 0.0) -> None:
        rate = max(1, rate_por_min)
        self._intervalo = (60.0 / rate) * (1.0 + max(0.0, folga))
        self._ultima: float | None = None

    async def aguardar(self) -> None:
        agora = time.monotonic()
        if self._ultima is not None:
            espera = self._intervalo - (agora - self._ultima)
            if espera > 0:
                await asyncio.sleep(espera)
        self._ultima = time.monotonic()


def novo_throttle() -> _Throttle:
    """Cria um throttle configurado pelo rate do plano CNPJá (use um por lote)."""
    return _Throttle(settings.cnpj_rate_por_min, settings.cnpj_rate_folga)


def validar_cnpj(cnpj: str) -> bool:
    """Valida o CNPJ pelos dígitos verificadores.

    Aceita o formato numérico tradicional e o alfanumérico (Receita Federal a partir
    de 2026): os 12 primeiros caracteres podem ser 0-9/A-Z e os 2 DVs são numéricos.
    O cálculo usa o valor ASCII menos 48 de cada caractere (compatível com ambos).
    """
    c = re.sub(r"[^0-9A-Za-z]", "", cnpj or "").upper()
    if len(c) != 14 or len(set(c)) == 1:
        return False
    if not c[12:].isdigit():  # os dois dígitos verificadores são sempre numéricos
        return False

    def _dv(base: str, pesos: list[int]) -> str:
        soma = sum((ord(ch) - 48) * p for ch, p in zip(base, pesos))
        resto = soma % 11
        return "0" if resto < 2 else str(11 - resto)

    dv1 = _dv(c[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    dv2 = _dv(c[:12] + dv1, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
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
    # Considera só records com taxId (evita KeyError em retorno inesperado da API).
    candidatos = [r for r in records if r.get("taxId")]
    matrizes = [r for r in candidatos if r.get("head")] or candidatos

    exatos = [r for r in matrizes if _normalizar(r.get("company", {}).get("name", "")) == alvo]
    raizes = {r["taxId"][:8] for r in matrizes}

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
        raise LookupError("Serviço de busca de CNPJ não disponível no momento.")
    return {"Authorization": settings.cnpj_lookup_api_key}


async def _get_com_retry(
    client: httpx.AsyncClient, url: str, params: dict, *, ok_404: bool = False
) -> httpx.Response:
    """GET com tratamento de 429: retry curto com backoff respeitando Retry-After.

    Faz até settings.cnpj_retry_max tentativas extras no 429. O tempo de espera é limitado
    por cnpj_retry_backoff_teto_s para não estourar o request HTTP síncrono. Esgotadas as
    tentativas, propaga RateLimitError (transitório) — o lote para e pede para aguardar.
    Crédito real esgotado (LookupError) não faz retry: é definitivo.
    """
    tentativa = 0
    while True:
        try:
            resp = await client.get(url, params=params, headers=_headers(), timeout=30)
        except httpx.HTTPError as exc:
            raise LookupError(f"Falha de rede na consulta de CNPJ: {exc}") from exc

        if resp.status_code == 401:
            raise LookupError("Serviço de busca de CNPJ indisponível (credencial).")
        if ok_404 and resp.status_code == 404:
            return resp
        if resp.status_code == 429:
            erro = _erro_de_429(resp)
            if not isinstance(erro, RateLimitError) or tentativa >= settings.cnpj_retry_max:
                raise erro
            tentativa += 1
            espera = erro.retry_after if erro.retry_after is not None else (
                settings.cnpj_retry_backoff_s * tentativa
            )
            espera = min(espera, settings.cnpj_retry_backoff_teto_s)
            logger.info("cnpj_lookup 429 (rate); retry %s em %.1fs", tentativa, espera)
            await asyncio.sleep(espera)
            continue
        if resp.status_code >= 400:
            raise LookupError(f"Erro {resp.status_code} na consulta de CNPJ.")
        return resp


async def buscar_por_nome(
    nome: str, uf: str | None, client: httpx.AsyncClient, throttle: "_Throttle | None" = None
) -> dict:
    """Busca CNPJ pela razão social (matrizes), com desambiguação. Consome créditos.

    Em lote, passe um throttle (novo_throttle()) para espaçar as chamadas sob o rate do plano.
    No 429 por taxa, propaga RateLimitError (transitório) após o retry interno; o chamador
    distingue de crédito esgotado (LookupError) e sinaliza corretamente ao usuário.
    """
    if throttle is not None:
        await throttle.aguardar()
    params = {"company.name.in": nome, "head.eq": "true", "limit": "10"}
    if uf:
        params["address.state.in"] = uf
    resp = await _get_com_retry(client, f"{settings.cnpj_lookup_base_url}/office", params)

    records = resp.json().get("records", [])
    resultado = melhor_match(nome, records)
    logger.info(
        "cnpj_lookup nome=%r uf=%s -> confianca=%s candidatos=%s",
        nome, uf, resultado["confianca"], resultado["n_candidatos"],
    )
    return resultado


async def consultar_cnpj(
    cnpj: str, client: httpx.AsyncClient, throttle: "_Throttle | None" = None
) -> dict:
    """Consulta dados do CNPJ (situação cadastral + Simples Nacional). Usa cache p/ economizar.

    Em lote (due diligence/reavaliação), passe um throttle para respeitar o rate do plano.
    Mesmo tratamento de 429 do buscar_por_nome: rate limit vira RateLimitError (transitório).
    """
    if throttle is not None:
        await throttle.aguardar()
    so_digitos = re.sub(r"\D", "", cnpj)
    params = {"simples": "true", "strategy": "CACHE_IF_FRESH", "maxAge": "30"}
    resp = await _get_com_retry(
        client, f"{settings.cnpj_lookup_base_url}/office/{so_digitos}", params, ok_404=True
    )
    if resp.status_code == 404:
        return {"cnpj": so_digitos, "encontrado": False}

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
        "fundacao": d.get("founded"),  # usado pelo score (maturidade do CNPJ)
    }
