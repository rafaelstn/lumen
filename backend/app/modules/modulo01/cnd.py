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
from app.modules.modulo01 import analises_repo, budget, fornecedores_repo
from app.modules.modulo01.jobs import store

logger = logging.getLogger("modulo01.cnd")


async def _sincronizar_historico(job_id: str) -> None:
    """Atualiza a Analise do histórico com o estado pós-CND/risco. Tolerante a falha.

    Chamado ao fim do lote para o histórico refletir CND e risco 2027. Falha de banco não
    afeta o lote (o estado essencial já está no JobStore).
    """
    job = store.obter(job_id)
    if job is None:
        return
    try:
        async with async_session_factory() as session:
            await analises_repo.salvar(session, job_id, job)
    except Exception:
        logger.warning(
            "CND: não foi possível sincronizar o histórico (job %s).", job_id[:8], exc_info=True
        )

# Status de regularidade fiscal.
NEGATIVA = "NEGATIVA"                                   # sem débitos, regular
POSITIVA_EFEITO_NEGATIVA = "POSITIVA_EFEITO_NEGATIVA"   # débito parcelado/suspenso
POSITIVA = "POSITIVA"                                   # débito ativo, irregular
FALHA = "FALHA"                                         # não foi possível consultar/indeterminado

# Classificação dos códigos de resposta da Infosimples (tabela oficial da doc da API).
# RE-TENTÁVEIS: falhas transitórias que a doc orienta repetir E que NÃO são cobradas — re-tentar
# tem chance de sucesso e é de graça. Ficam DE FORA: codes que cobram (re-tentar inflaria a fatura
# à toa) e erros de parâmetro/token nossos (nunca resolvem sozinhos).
#   600 erro inesperado | 605 timeout no limite | 609 tentativas à origem excedidas |
#   610 falha de captcha | 613 origem bloqueou ("tente de novo") | 614 erro inesperado na origem |
#   615 origem indisponível | 617 sobrecarga do serviço | 618 origem sobrecarregada.
# (Falha de rede/timeout HTTP não tem code: já é tratada como transitória no except, abaixo.)
_CODES_TRANSITORIOS = {600, 605, 609, 610, 613, 614, 615, 617, 618}

# Codes que indicam falha da FONTE (Receita Federal/PGFN), não defeito nosso. A UI usa isso para
# avisar "a Receita está instável, tente novamente em alguns minutos" em vez de "erro do sistema".
# Inclui o 611 (certidão incompleta na origem) e o 612 (origem não retornou dados): esses COBRAM,
# então ficam fora dos re-tentáveis (não martelar gerando fatura), mas SÃO instabilidade da origem.
_CODES_ORIGEM_FORA = {611, 612, 613, 614, 615, 617, 618}


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


async def _consultar_cnd_uma_vez(cnpj: str, client: httpx.AsyncClient) -> dict:
    """Uma tentativa de consulta da CND federal de um CNPJ. Nunca lança.

    Devolve sempre um dict com `status`. Em falha, inclui `cnd_falha_motivo` (texto legível,
    sem dado sensível) e `_transitoria` (bool interno: orienta o retry; não vai pro cliente).
    Em sucesso, captura todos os campos úteis retornados pela Infosimples.
    """
    so_digitos = re.sub(r"\D", "", cnpj or "")
    payload = {
        "token": settings.infosimples_token,
        "cnpj": so_digitos,
        "timeout": str(settings.infosimples_timeout),
    }
    # Por padrão pedimos para a fonte NÃO gerar o comprovante (sem custo/tempo extra de render).
    if not settings.cnd_capturar_comprovante:
        payload["ignore_site_receipt"] = "1"
    base = {"cnpj": so_digitos, "data_consulta": datetime.now(timezone.utc).isoformat()}
    try:
        resp = await client.post(
            f"{settings.infosimples_base_url}/{settings.cnd_servico}",
            data=payload,
            timeout=settings.infosimples_timeout + 30,
        )
        body = resp.json()
    except (httpx.TimeoutException,) as exc:
        logger.warning("CND timeout cnpj=%s: %s", _mascara_cnpj(so_digitos), exc)
        return {
            **base, "status": FALHA, "descricao": "Tempo de resposta excedido na fonte.",
            "cnd_falha_motivo": "Tempo de resposta excedido na consulta à Receita/PGFN.",
            "_transitoria": True, "cobrada": False,  # sem resposta da origem: não há cobrança
        }
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("CND falha de rede cnpj=%s: %s", _mascara_cnpj(so_digitos), exc)
        return {
            **base, "status": FALHA, "descricao": "Falha de comunicação com a fonte.",
            "cnd_falha_motivo": "Falha de comunicação com a fonte de consulta.",
            "_transitoria": True, "cobrada": False,  # sem resposta da origem: não há cobrança
        }

    # Cobrança autoritativa: a própria Infosimples informa se a requisição foi faturada
    # (header.billable). Vários codes de FALHA COBRAM (611/612/606/607/608/619/620), então
    # não dá para contar custo por "deu certo": usamos este flag para o audit trail.
    cobrada = bool((body.get("header") or {}).get("billable"))

    code = body.get("code")
    if code != 200 or not body.get("data"):
        motivo = (body.get("code_message") or "Consulta sem resultado.").strip()
        transitoria = code in _CODES_TRANSITORIOS
        origem_fora = code in _CODES_ORIGEM_FORA
        logger.info(
            "CND sem resultado cnpj=%s code=%s transitoria=%s origem_fora=%s cobrada=%s",
            _mascara_cnpj(so_digitos), code, transitoria, origem_fora, cobrada,
        )
        return {
            **base, "status": FALHA, "descricao": motivo,
            "cnd_falha_motivo": motivo, "_transitoria": transitoria,
            "_origem_fora": origem_fora, "cobrada": cobrada,
        }

    item = body["data"][0]
    status = _mapear_status(item)
    logger.info("CND cnpj=%s status=%s cobrada=%s", _mascara_cnpj(so_digitos), status, cobrada)
    return {
        **base,
        "status": status,
        "cobrada": cobrada,
        "descricao": item.get("descricao") or item.get("situacao") or "",
        # Campos completos da certidão (alimentam o dashboard e o relatório).
        "cnd_tipo": item.get("certidao"),
        "certidao_codigo": item.get("certidao_codigo"),
        "cnd_debitos_rfb": bool(item.get("debitos_rfb")) if item.get("debitos_rfb") is not None else None,
        "cnd_debitos_pgfn": bool(item.get("debitos_pgfn")) if item.get("debitos_pgfn") is not None else None,
        "cnd_emissao_data": item.get("emissao_data"),
        "validade_data": item.get("validade_data") or item.get("validade"),
        "cnd_consulta_datahora": item.get("consulta_datahora"),
        # Link do PDF oficial. Vem null quando enviamos ignore_site_receipt=1.
        "cnd_comprovante_url": item.get("site_receipt"),
    }


async def consultar_cnd(cnpj: str, client: httpx.AsyncClient) -> dict:
    """Consulta a CND federal de um CNPJ com retry de falha TRANSITÓRIA. Nunca lança.

    Re-tenta (com backoff exponencial limitado por `cnd_retry_backoff_teto_s`) apenas quando a
    falha é transitória (timeout, 429, 5xx, erro de rede, code de instabilidade da fonte). Falha
    definitiva (CNPJ inválido, code de negócio) e sucesso retornam de imediato. O teto de
    tentativas é `1 + cnd_retry_max`. O campo interno `_transitoria` é removido do retorno.
    """
    tentativas = max(0, settings.cnd_retry_max) + 1
    r: dict = {}
    for i in range(tentativas):
        r = await _consultar_cnd_uma_vez(cnpj, client)
        if r["status"] != FALHA or not r.get("_transitoria"):
            break
        if i < tentativas - 1:
            espera = min(
                settings.cnd_retry_backoff_s * (2 ** i),
                settings.cnd_retry_backoff_teto_s,
            )
            logger.info(
                "CND retry cnpj=%s tentativa=%d/%d espera=%.1fs",
                _mascara_cnpj(cnpj), i + 1, tentativas - 1, espera,
            )
            await asyncio.sleep(espera)
    r.pop("_transitoria", None)
    # Promove a flag interna a campo público estável: indica que a falha foi por a FONTE
    # (Receita/PGFN) estar fora do ar, para o chamador avisar o usuário corretamente.
    r["origem_fora"] = bool(r.pop("_origem_fora", False))
    return r


# Referências de tasks em andamento (evita coleta pelo GC).
_tasks: set[asyncio.Task] = set()


def _precisa_consultar(f: dict) -> bool:
    """Alvo de CND: tem CNPJ e ainda não tem um RESULTADO VÁLIDO. Resultado válido
    (negativa/positiva) é pulado para não regastar; FALHA é re-tentado (ex: a Receita
    estava fora do ar, então a consulta anterior não conta como resultado)."""
    return bool(f.get("cnpj")) and f.get("status_cnd") in (None, "", FALHA)


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
        com_cnpj = [f for f in fornecedores if _precisa_consultar(f)]
        alvos = [(f["cod_forn"], f["cnpj"]) for f in com_cnpj[:limite]]
        total = len(alvos)
        info.update(status="iniciado", total=total, total_com_cnpj=len(com_cnpj), alvos=alvos)
        job["cnd_progresso"] = {
            "total": total,
            "total_com_cnpj": len(com_cnpj),
            "consultados": 0,
            "falhas": 0,
            # Quantas consultas a Infosimples efetivamente FATUROU (header.billable). Inclui
            # falhas que cobram (611/612/606...). É o número usado no audit trail de custo.
            "cobradas": 0,
            # Quantas falhas foram por a FONTE (Receita/PGFN) estar fora do ar (code 615 e
            # afins). > 0 sinaliza ao frontend "a Receita está temporariamente fora do ar"
            # em vez de "defeito do sistema".
            "origem_indisponivel": 0,
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
                    r = {
                        "status": FALHA,
                        "descricao": "Teto diário de consultas atingido.",
                        "cnd_falha_motivo": "Teto diário de consultas atingido.",
                    }
                else:
                    r = await consultar_cnd(cnpj, client)

            # Capturado dentro do lock para persistir o metadado de CND fora dele depois.
            cap: dict = {}

            def aplicar(job: dict) -> None:
                for f in job["fornecedores"]:
                    if f["cod_forn"] == cod_forn:
                        f["status_cnd"] = r["status"]
                        f["cnd_descricao"] = r.get("descricao")
                        # Campos completos da certidão (None em FALHA, exceto o motivo).
                        f["cnd_tipo"] = r.get("cnd_tipo")
                        f["cnd_certidao_codigo"] = r.get("certidao_codigo")
                        f["cnd_emissao_data"] = r.get("cnd_emissao_data")
                        f["cnd_validade"] = r.get("validade_data")
                        f["cnd_consulta_datahora"] = r.get("cnd_consulta_datahora")
                        f["cnd_debitos_rfb"] = r.get("cnd_debitos_rfb")
                        f["cnd_debitos_pgfn"] = r.get("cnd_debitos_pgfn")
                        f["cnd_comprovante_url"] = r.get("cnd_comprovante_url")
                        f["cnd_falha_motivo"] = r.get("cnd_falha_motivo")
                        # Flag autoritativo (pela tabela de codes) de que a falha é da FONTE
                        # (Receita/PGFN), não nossa. O frontend usa isso em vez de adivinhar
                        # pelo texto do motivo. Persiste no histórico junto com o fornecedor.
                        f["cnd_origem_fora"] = bool(r.get("origem_fora"))
                        cap["razao_social"] = f.get("nome_forn")
                        break
                prog = job.get("cnd_progresso") or {
                    "total": total, "consultados": 0, "falhas": 0, "origem_indisponivel": 0,
                }
                prog.setdefault("origem_indisponivel", 0)
                prog.setdefault("cobradas", 0)
                prog["consultados"] = prog.get("consultados", 0) + 1
                if r.get("cobrada"):
                    prog["cobradas"] += 1
                if r["status"] == FALHA:
                    prog["falhas"] = prog.get("falhas", 0) + 1
                    if r.get("origem_fora"):
                        prog["origem_indisponivel"] = prog.get("origem_indisponivel", 0) + 1
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
        # Custo real = consultas FATURADAS pela Infosimples (header.billable), não "consultados
        # - falhas": várias falhas (611/612...) cobram. Usar o billable evita subestimar a fatura.
        capturado["cobradas"] = prog.get("cobradas", 0)

    if not store.mutar(job_id, finalizar):
        logger.warning("CND: job %s expirou antes de aplicar o risco 2027.", job_id)

    # Audit trail do consumo do lote de CND. Resiliente: o gasto na Infosimples já ocorreu.
    from app.modules.consumo import repo as consumo_repo

    # Tenant dono do job (multi-tenant). Fallback no default preserva o comportamento quando
    # a flag de auth está desligada. Espelha o enriquecimento: o custo é atribuído a quem gastou.
    job_atual = store.obter(job_id) or {}
    escritorio_id = job_atual.get("escritorio_id") or settings.escritorio_default_id

    try:
        await consumo_repo.registrar_cnd(
            escritorio_id=escritorio_id, modulo="modulo01",
            operacao="cnd_lote", consultas_cobradas=capturado.get("cobradas", 0),
            contexto=f"job {job_id[:8]}",
        )
    except Exception:
        logger.warning("CND: falha ao registrar consumo do lote (job %s).", job_id[:8], exc_info=True)

    # Mantém o histórico em sincronia com o estado pós-CND/risco.
    await _sincronizar_historico(job_id)


async def consultar_cnd_fornecedor(job_id: str, cod_forn: str) -> dict | None:
    """Re-consulta a CND de UM fornecedor, sob demanda (botão na ficha). Síncrono: é uma única
    consulta, então não usa background/progresso. Atualiza o fornecedor no store, recalcula o
    risco 2027, contabiliza o custo (se cobrada) e sincroniza o histórico. Devolve o fornecedor
    atualizado, ou None se o job/fornecedor não existir (ou não tiver CNPJ). Nunca lança.
    """
    from app.modules.modulo01 import risk

    job = store.obter(job_id)
    if job is None:
        return None
    alvo = next((f for f in job["fornecedores"] if f.get("cod_forn") == cod_forn), None)
    if alvo is None or not alvo.get("cnpj"):
        return None

    cnpj = alvo["cnpj"]
    if not budget.consumir("cnd"):
        r = {
            "status": FALHA, "descricao": "Teto diário de consultas atingido.",
            "cnd_falha_motivo": "Teto diário de consultas atingido.", "cobrada": False,
        }
    else:
        async with httpx.AsyncClient() as client:
            r = await consultar_cnd(cnpj, client)

    cap: dict = {}

    def aplicar(job: dict) -> None:
        for f in job["fornecedores"]:
            if f["cod_forn"] == cod_forn:
                f["status_cnd"] = r["status"]
                f["cnd_descricao"] = r.get("descricao")
                f["cnd_tipo"] = r.get("cnd_tipo")
                f["cnd_certidao_codigo"] = r.get("certidao_codigo")
                f["cnd_emissao_data"] = r.get("cnd_emissao_data")
                f["cnd_validade"] = r.get("validade_data")
                f["cnd_consulta_datahora"] = r.get("cnd_consulta_datahora")
                f["cnd_debitos_rfb"] = r.get("cnd_debitos_rfb")
                f["cnd_debitos_pgfn"] = r.get("cnd_debitos_pgfn")
                f["cnd_comprovante_url"] = r.get("cnd_comprovante_url")
                f["cnd_falha_motivo"] = r.get("cnd_falha_motivo")
                f["cnd_origem_fora"] = bool(r.get("origem_fora"))
                cap["razao_social"] = f.get("nome_forn")
                break
        # Recalcula o risco com o novo status (a engine opera na lista inteira, sem efeito colateral).
        risk.aplicar_risco(job["fornecedores"])

    if not store.mutar(job_id, aplicar):
        return None

    # Metadado por CNPJ (só status real; FALHA não atualiza a data). Tolerante a banco fora.
    if r["status"] != FALHA:
        try:
            async with async_session_factory() as session:
                await fornecedores_repo.registrar_cnd(
                    session, cnpj, r["status"], razao_social=cap.get("razao_social")
                )
        except Exception:
            logger.warning("CND (individual): falha ao registrar metadado por CNPJ.", exc_info=True)

    # Audit trail: só registra se a Infosimples faturou esta consulta (billable).
    if r.get("cobrada"):
        from app.modules.consumo import repo as consumo_repo

        job_atual = store.obter(job_id) or {}
        escritorio_id = job_atual.get("escritorio_id") or settings.escritorio_default_id
        try:
            await consumo_repo.registrar_cnd(
                escritorio_id=escritorio_id, modulo="modulo01",
                operacao="cnd_individual", consultas_cobradas=1, contexto=f"job {job_id[:8]}",
            )
        except Exception:
            logger.warning("CND (individual): falha ao registrar consumo.", exc_info=True)

    await _sincronizar_historico(job_id)
    job_final = store.obter(job_id) or {}
    return next((f for f in job_final["fornecedores"] if f["cod_forn"] == cod_forn), None)
