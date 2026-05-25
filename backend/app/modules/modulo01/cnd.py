"""Consulta de CND (regularidade fiscal) via Infosimples — Receita Federal/PGFN. Fase 3.

Substitui o scraping com Playwright+captcha do briefing: a Infosimples lida com o
portal e o captcha do lado dela e entrega JSON. Mais robusto e sem manutenção de scraper.

Concorrência: a task escreve cada resultado via store.mutar (atômico, sob lock);
leituras (/resultado, /progresso) recebem cópia. Idempotência: só uma consulta por job
de cada vez. Custo: cada consulta paga passa pelo teto global de orçamento.
"""
import asyncio
import logging
import re
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.database import async_session_factory
from app.modules.modulo01 import budget, fornecedores_repo
from app.modules.modulo01.jobs import store

logger = logging.getLogger("modulo01.cnd")

# Status de regularidade fiscal.
NEGATIVA = "NEGATIVA"                                   # sem débitos — regular
POSITIVA_EFEITO_NEGATIVA = "POSITIVA_EFEITO_NEGATIVA"   # débito parcelado/suspenso
POSITIVA = "POSITIVA"                                   # débito ativo — irregular
FALHA = "FALHA"                                         # não foi possível consultar/indeterminado

_SERVICO = "receita-federal/pgfn"


def _mascara_cnpj(cnpj: str) -> str:
    """Mascara o CNPJ para log (não expõe o número completo associado a débito)."""
    d = re.sub(r"\D", "", cnpj or "")
    return f"{d[:2]}.***.***/{d[-2:]}" if len(d) == 14 else "***"


def _tem_debitos(item: dict) -> bool:
    return bool(item.get("debitos_rfb")) or bool(item.get("debitos_pgfn"))


def _mapear_status(item: dict) -> str:
    conseguiu = item.get("conseguiu_emitir_certidao_negativa")
    if conseguiu is True:
        return POSITIVA_EFEITO_NEGATIVA if _tem_debitos(item) else NEGATIVA
    if conseguiu is False:
        return POSITIVA
    # Campo ausente/indeterminado: não assume regularidade — marca FALHA.
    return FALHA


async def consultar_cnd(cnpj: str, client: httpx.AsyncClient) -> dict:
    """Consulta a CND federal de um CNPJ. Nunca lança: falha vira status FALHA."""
    so_digitos = re.sub(r"\D", "", cnpj or "")
    payload = {
        "token": settings.infosimples_token,
        "cnpj": so_digitos,
        "timeout": str(settings.infosimples_timeout),
        "ignore_site_receipt": "1",
    }
    base = {"cnpj": so_digitos, "data_consulta": datetime.now(timezone.utc).isoformat()}
    try:
        resp = await client.post(
            f"{settings.infosimples_base_url}/{_SERVICO}",
            data=payload,
            timeout=settings.infosimples_timeout + 30,
        )
        body = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("CND falha de rede cnpj=%s: %s", _mascara_cnpj(so_digitos), exc)
        return {**base, "status": FALHA, "descricao": "Falha de comunicação com a fonte."}

    code = body.get("code")
    if code != 200 or not body.get("data"):
        logger.info("CND sem resultado cnpj=%s code=%s", _mascara_cnpj(so_digitos), code)
        return {**base, "status": FALHA, "descricao": body.get("code_message", "Consulta sem resultado.")}

    item = body["data"][0]
    status = _mapear_status(item)
    logger.info("CND cnpj=%s status=%s", _mascara_cnpj(so_digitos), status)
    return {
        **base,
        "status": status,
        "descricao": item.get("descricao") or item.get("situacao") or "",
        "certidao_codigo": item.get("certidao_codigo"),
        "validade_data": item.get("validade_data"),
    }


# Referências de tasks em andamento (evita coleta pelo GC).
_tasks: set[asyncio.Task] = set()


def iniciar_consulta_job(job_id: str, limite: int) -> dict:
    """Inicia a consulta de CND em background. Idempotente: não dispara se já em andamento.

    Retorna {status: iniciado|ja_em_andamento|nao_encontrado, total, total_com_cnpj}.
    """
    info: dict = {}

    def _preparar(job: dict) -> None:
        prog = job.get("cnd_progresso")
        if prog and prog.get("status") == "em_andamento":
            info["status"] = "ja_em_andamento"
            return
        fornecedores = job["fornecedores"]
        com_cnpj = [f for f in fornecedores if f.get("cnpj") and not f.get("status_cnd")]
        alvos = [(f["cod_forn"], f["cnpj"]) for f in com_cnpj[:limite]]
        total = len(alvos)
        info.update(status="iniciado", total=total, total_com_cnpj=len(com_cnpj), alvos=alvos)
        job["cnd_progresso"] = {
            "total": total,
            "total_com_cnpj": len(com_cnpj),
            "consultados": 0,
            "falhas": 0,
            "percentual": 0.0 if total else 100.0,
            "status": "em_andamento" if total else "concluido",
        }

    if not store.mutar(job_id, _preparar):
        return {"status": "nao_encontrado"}
    if info.get("status") == "ja_em_andamento":
        return {"status": "ja_em_andamento"}

    total = info["total"]
    if total:
        task = asyncio.create_task(_processar(job_id, info["alvos"], total))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)
    return {"status": "iniciado", "total": total, "total_com_cnpj": info["total_com_cnpj"]}


async def _processar(job_id: str, alvos: list[tuple[str, str]], total: int) -> None:
    sem = asyncio.Semaphore(settings.cnd_concorrencia)

    async with httpx.AsyncClient() as client:
        async def um(cod_forn: str, cnpj: str) -> None:
            async with sem:
                if not budget.consumir("cnd"):
                    r = {"status": FALHA, "descricao": "Teto diário de consultas atingido."}
                else:
                    r = await consultar_cnd(cnpj, client)

            # Capturado dentro do lock para persistir o metadado de CND fora dele depois.
            cap: dict = {}

            def aplicar(job: dict) -> None:
                for f in job["fornecedores"]:
                    if f["cod_forn"] == cod_forn:
                        f["status_cnd"] = r["status"]
                        f["cnd_descricao"] = r.get("descricao")
                        cap["razao_social"] = f.get("nome_forn")
                        break
                prog = job.get("cnd_progresso") or {"total": total, "consultados": 0, "falhas": 0}
                prog["consultados"] = prog.get("consultados", 0) + 1
                if r["status"] == FALHA:
                    prog["falhas"] = prog.get("falhas", 0) + 1
                prog["percentual"] = round(prog["consultados"] / total * 100, 1) if total else 100.0
                if prog["consultados"] >= total:
                    prog["status"] = "concluido"
                job["cnd_progresso"] = prog

            if not store.mutar(job_id, aplicar):
                logger.warning("CND: job %s expirou durante a consulta; resultado descartado.", job_id)
                return

            # Registra por CNPJ quando/qual foi a última CND consultada (metadado de controle).
            # Só com status real: FALHA não atualiza a data para não mascarar o que é recente.
            # Tolerante: o banco fora do ar não derruba a consulta (o resultado já está no store).
            if cnpj and r["status"] != FALHA:
                try:
                    async with async_session_factory() as session:
                        await fornecedores_repo.registrar_cnd(
                            session, cnpj, r["status"], razao_social=cap.get("razao_social")
                        )
                except Exception:
                    logger.warning("CND: falha ao registrar metadado por CNPJ (job %s).", job_id[:8], exc_info=True)

        await asyncio.gather(*[um(cod, cnpj) for cod, cnpj in alvos])

    # Fase 4: calcula o risco 2027 após ter os status de CND.
    from app.modules.modulo01 import risk

    capturado: dict = {}

    def finalizar(job: dict) -> None:
        risk.aplicar_risco(job["fornecedores"])
        prog = job.get("cnd_progresso") or {}
        prog["status"] = "concluido"
        prog["percentual"] = 100.0
        job["cnd_progresso"] = prog
        # CNDs concluídas (com crédito) = consultados - falhas. FALHA não consome crédito.
        capturado["concluidas"] = max(0, prog.get("consultados", 0) - prog.get("falhas", 0))

    if not store.mutar(job_id, finalizar):
        logger.warning("CND: job %s expirou antes de aplicar o risco 2027.", job_id)

    # Audit trail do consumo do lote de CND. Resiliente: o gasto na Infosimples já ocorreu.
    from app.config import settings
    from app.modules.consumo import repo as consumo_repo

    try:
        await consumo_repo.registrar_cnd(
            escritorio_id=settings.escritorio_default_id, modulo="modulo01",
            operacao="cnd_lote", consultas_concluidas=capturado.get("concluidas", 0),
            contexto=f"job {job_id[:8]}",
        )
    except Exception:
        logger.warning("CND: falha ao registrar consumo do lote (job %s).", job_id[:8], exc_info=True)
