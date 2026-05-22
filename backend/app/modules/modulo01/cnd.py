"""Consulta de CND (regularidade fiscal) via Infosimples — Receita Federal/PGFN. Fase 3.

Substitui o scraping com Playwright+captcha do briefing: a Infosimples lida com o
portal e o captcha do lado dela e entrega JSON. Mais robusto e sem manutenção de scraper.
"""
import asyncio
import logging
import re
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.modules.modulo01.jobs import store

logger = logging.getLogger("modulo01.cnd")

# Status de regularidade fiscal.
NEGATIVA = "NEGATIVA"                          # sem débitos — regular
POSITIVA_EFEITO_NEGATIVA = "POSITIVA_EFEITO_NEGATIVA"  # débito parcelado/suspenso
POSITIVA = "POSITIVA"                          # débito ativo — irregular
FALHA = "FALHA"                                # não foi possível consultar

_SERVICO = "receita-federal/pgfn"


def _tem_debitos(item: dict) -> bool:
    for chave in ("debitos_rfb", "debitos_pgfn"):
        v = item.get(chave)
        if v:  # lista/string não-vazia
            return True
    return False


def _mapear_status(item: dict) -> str:
    conseguiu = item.get("conseguiu_emitir_certidao_negativa")
    if conseguiu is False:
        return POSITIVA
    if _tem_debitos(item):
        return POSITIVA_EFEITO_NEGATIVA
    return NEGATIVA


async def consultar_cnd(cnpj: str, client: httpx.AsyncClient) -> dict:
    """Consulta a CND federal de um CNPJ. Nunca lança: falha vira status FALHA."""
    so_digitos = re.sub(r"\D", "", cnpj or "")
    payload = {
        "token": settings.infosimples_token,
        "cnpj": so_digitos,
        "timeout": str(settings.infosimples_timeout),
        "ignore_site_receipt": "1",
    }
    base = {
        "cnpj": so_digitos,
        "data_consulta": datetime.now(timezone.utc).isoformat(),
    }
    try:
        resp = await client.post(
            f"{settings.infosimples_base_url}/{_SERVICO}",
            data=payload,
            timeout=settings.infosimples_timeout + 30,
        )
        body = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("CND falha de rede cnpj=%s: %s", so_digitos, exc)
        return {**base, "status": FALHA, "descricao": "Falha de comunicação com a fonte."}

    code = body.get("code")
    if code != 200 or not body.get("data"):
        logger.info("CND sem resultado cnpj=%s code=%s", so_digitos, code)
        return {**base, "status": FALHA, "descricao": body.get("code_message", "Consulta sem resultado.")}

    item = body["data"][0]
    status = _mapear_status(item)
    logger.info("CND cnpj=%s status=%s", so_digitos, status)
    return {
        **base,
        "status": status,
        "descricao": item.get("descricao") or item.get("situacao") or "",
        "certidao_codigo": item.get("certidao_codigo"),
        "validade_data": item.get("validade_data"),
    }


# Referências de tasks em andamento (evita coleta pelo GC).
_tasks: set[asyncio.Task] = set()


def iniciar_consulta_job(job_id: str, limite: int) -> int:
    """Dispara a consulta de CND em background para os fornecedores com CNPJ. Devolve o total."""
    job = store.obter(job_id)
    if job is None:
        return 0
    fornecedores = job["fornecedores"]
    alvos = [f for f in fornecedores if f.get("cnpj") and not f.get("status_cnd")][:limite]
    total = len(alvos)
    store.atualizar(
        job_id,
        cnd_progresso={"total": total, "consultados": 0, "falhas": 0, "percentual": 0.0, "status": "em_andamento"},
    )
    if total:
        task = asyncio.create_task(_processar(job_id, fornecedores, alvos, total))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)
    else:
        store.atualizar(job_id, cnd_progresso={"total": 0, "consultados": 0, "falhas": 0, "percentual": 100.0, "status": "concluido"})
    return total


async def _processar(job_id: str, fornecedores: list, alvos: list, total: int) -> None:
    sem = asyncio.Semaphore(settings.cnd_concorrencia)
    estado = {"consultados": 0, "falhas": 0}

    async with httpx.AsyncClient() as client:
        async def um(f: dict) -> None:
            async with sem:
                r = await consultar_cnd(f["cnpj"], client)
            f["status_cnd"] = r["status"]
            f["cnd_descricao"] = r.get("descricao")
            estado["consultados"] += 1
            if r["status"] == FALHA:
                estado["falhas"] += 1
            store.atualizar(
                job_id,
                cnd_progresso={
                    "total": total,
                    "consultados": estado["consultados"],
                    "falhas": estado["falhas"],
                    "percentual": round(estado["consultados"] / total * 100, 1),
                    "status": "em_andamento",
                },
            )

        await asyncio.gather(*[um(f) for f in alvos])

    # Fase 4: calcula o risco 2027 após ter os status de CND.
    from app.modules.modulo01 import risk

    risk.aplicar_risco(fornecedores)
    store.atualizar(
        job_id,
        fornecedores=fornecedores,
        cnd_progresso={
            "total": total,
            "consultados": estado["consultados"],
            "falhas": estado["falhas"],
            "percentual": 100.0,
            "status": "concluido",
        },
    )
