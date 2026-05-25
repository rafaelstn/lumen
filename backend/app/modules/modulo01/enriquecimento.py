"""Enriquecimento de CNPJ em background: busca por razão social TODOS os pendentes do job.

Espelha o padrão da CND (cnd.py): iniciar_*_job dispara asyncio.create_task(_processar(...)),
grava progresso no store via store.mutar (atômico, sob lock), e o frontend faz polling.

Diferença para a CND: aqui as chamadas à CNPJá são SEQUENCIAIS e espaçadas por um throttle
(novo_throttle(), respeita cnpj_rate_por_min), porque o objetivo é não estourar o rate do
plano ao processar dezenas de pendentes de uma vez. Por ser background, não há timeout de
request HTTP, então não existe mais o teto de 8 por clique: processa todos até o limite_max
de segurança por job.

Custo: cada busca paga passa pelo teto global diário (budget). O que não chega a ser
consultado (rate limit/crédito esgotado) é estornado, mantendo o teto fiel ao gasto real.
Idempotência: só um enriquecimento por job de cada vez.
"""
import asyncio
import logging

import httpx

from app.config import settings
from app.database import async_session_factory
from app.modules.modulo01 import analises_repo, budget, cnpj_lookup, fornecedores_repo
from app.modules.modulo01.jobs import store

logger = logging.getLogger("modulo01.enriquecimento")

# Referências de tasks em andamento (evita coleta pelo GC).
_tasks: set[asyncio.Task] = set()


async def _sincronizar_historico(job_id: str) -> None:
    """Atualiza a Analise do histórico com o estado atual do job. Tolerante a falha.

    Chamado ao fim do lote para o histórico refletir os CNPJ casados. Falha de banco não
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
            "Enriquecimento: não foi possível sincronizar o histórico (job %s).", job_id[:8], exc_info=True
        )


def _progresso_inicial(total: int) -> dict:
    return {
        "total": total,
        "processados": 0,
        "confirmados": 0,
        "baixa_confianca": 0,
        "ambiguos": 0,
        "nao_encontrados": 0,
        "erros_pontuais": 0,
        "percentual": 0.0 if total else 100.0,
        "status": "em_andamento" if total else "concluido",
        "creditos_esgotados": False,
        "limite_taxa_atingido": False,
        "teto_diario_atingido": False,
    }


def iniciar_enriquecimento_job(job_id: str, limite: int) -> dict:
    """Inicia o enriquecimento de CNPJ em background. Idempotente: não dispara se já em andamento.

    `limite` é o teto de segurança por job (clamp em cnpj_lookup_limite_max). Processa TODOS
    os pendentes (sem CNPJ) até esse teto — não há mais teto por clique.

    Retorna {status: iniciado|ja_em_andamento|nao_encontrado, total}.
    """
    info: dict = {}

    def _preparar(job: dict) -> None:
        prog = job.get("enriquecimento_progresso")
        if prog and prog.get("status") == "em_andamento":
            info["status"] = "ja_em_andamento"
            return
        pendentes = [
            (f["cod_forn"], f["nome_forn"]) for f in job["fornecedores"] if not f.get("cnpj")
        ][:limite]
        total = len(pendentes)
        info.update(status="iniciado", total=total, pendentes=pendentes)
        job["enriquecimento_progresso"] = _progresso_inicial(total)

    if not store.mutar(job_id, _preparar):
        return {"status": "nao_encontrado"}
    if info.get("status") == "ja_em_andamento":
        return {"status": "ja_em_andamento"}

    total = info["total"]
    if total:
        task = asyncio.create_task(_processar(job_id, info["pendentes"]))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)
    return {"status": "iniciado", "total": total}


def _classificar(prog: dict, achados: dict, cod_forn: str, nome: str, r: dict) -> None:
    """Atualiza as contagens do progresso e registra o achado confirmável. Sob o lock do store."""
    prog["processados"] += 1
    conf = r["confianca"]
    if conf in (cnpj_lookup.CONF_ALTA, cnpj_lookup.CONF_BAIXA):
        confirmado = conf == cnpj_lookup.CONF_ALTA
        # Guarda também o cadastro completo (vem no MESMO retorno da busca, sem crédito extra).
        achados[cod_forn] = {
            "cnpj": r["cnpj"],
            "confirmado": confirmado,
            "nome_oficial": r.get("nome_oficial") or nome,
            "nome_entrada": nome,
            "cadastro": r.get("cadastro"),
        }
        prog["confirmados" if confirmado else "baixa_confianca"] += 1
    elif conf == cnpj_lookup.CONF_AMBIGUO:
        prog["ambiguos"] += 1
    else:
        prog["nao_encontrados"] += 1


async def _processar(job_id: str, pendentes: list[tuple[str, str]]) -> None:
    """Task de background: busca cada pendente sob throttle, aplica e persiste incrementalmente."""
    total = len(pendentes)
    throttle = cnpj_lookup.novo_throttle()
    # cod_forn -> (cnpj, confirmado, nome_oficial, nome_entrada); acumula para persistir ao fim.
    achados: dict[str, tuple[str, bool, str, str]] = {}
    consumidos = 0  # buscas que efetivamente foram à CNPJá (para o audit trail)
    parada = None   # "creditos_esgotados" | "limite_taxa_atingido" | "teto_diario_atingido"

    async with httpx.AsyncClient() as client:
        for cod_forn, nome in pendentes:
            if not budget.consumir("cnpj"):
                parada = "teto_diario_atingido"
                break
            try:
                r = await cnpj_lookup.buscar_por_nome(nome, None, client, throttle=throttle)
            except cnpj_lookup.RateLimitError:
                # Transitório: o throttle deveria evitar, mas por segurança paramos o lote,
                # preservamos o que já casou e devolvemos o crédito não usado.
                budget.devolver("cnpj")
                parada = "limite_taxa_atingido"
                break
            except cnpj_lookup.LookupError as exc:
                if "rédit" in str(exc):  # crédito real esgotado (definitivo)
                    budget.devolver("cnpj")
                    parada = "creditos_esgotados"
                    break
                # Erro pontual (rede/4xx/5xx): a busca contou como tentativa paga. Segue o lote.
                consumidos += 1

                def _erro(job: dict) -> None:
                    prog = job.get("enriquecimento_progresso")
                    if prog is not None:
                        prog["erros_pontuais"] += 1

                store.mutar(job_id, _erro)
                continue

            consumidos += 1

            def _aplicar(job: dict, _cod=cod_forn, _nome=nome, _r=r) -> None:
                prog = job.get("enriquecimento_progresso")
                if prog is None:  # job mutado de forma inesperada; nada a fazer
                    return
                _classificar(prog, achados, _cod, _nome, _r)
                # Aplica o achado já no fornecedor para o /resultado refletir incrementalmente.
                if _cod in achados:
                    a = achados[_cod]
                    for f in job["fornecedores"]:
                        if f["cod_forn"] == _cod:
                            f["cnpj"] = a["cnpj"]
                            f["cnpj_pendente"] = False
                            f["cnpj_confirmado"] = a["confirmado"]
                            break
                prog["percentual"] = round(prog["processados"] / total * 100, 1) if total else 100.0

            if not store.mutar(job_id, _aplicar):
                logger.warning("Enriquecimento: job %s expirou durante o lote; abortando.", job_id[:8])
                return

    # Finaliza o progresso no store (status concluido + flags de parada, se houve).
    def _finalizar(job: dict) -> None:
        prog = job.get("enriquecimento_progresso")
        if prog is None:
            return
        prog["status"] = "concluido"
        prog["percentual"] = 100.0
        if parada:
            prog[parada] = True

    store.mutar(job_id, _finalizar)

    await _persistir(job_id, achados, consumidos)

    # Mantém o histórico em sincronia com o estado pós-enriquecimento (CNPJ casados).
    await _sincronizar_historico(job_id)


async def _persistir(job_id: str, achados: dict, consumidos: int) -> None:
    """Salva os CNPJ resolvidos + aliases no banco e registra o audit trail. Tolerante a falha.

    O dado essencial (CNPJ casado) já está no store; falha de banco/consumo não derruba o lote.
    """
    if achados:
        try:
            async with async_session_factory() as session:
                for a in achados.values():
                    cadastro = a.get("cadastro")
                    if cadastro and cadastro.get("cnpj"):
                        # Grava o cadastro COMPLETO (endereço/contato/atividade/sócios) que veio
                        # no mesmo retorno da busca por nome, sem custo extra de crédito.
                        await fornecedores_repo.salvar_cadastro(session, cadastro, "cnpja")
                    else:
                        # Fallback (cadastro indisponível no retorno): mantém o cache mínimo.
                        await fornecedores_repo.upsert(session, a["cnpj"], a["nome_oficial"], "cnpja")
                    # Alias do NOME DE ENTRADA do arquivo: a re-análise casa de graça mesmo
                    # quando o nome oficial salvo difere da grafia do arquivo.
                    await fornecedores_repo.registrar_alias(session, a["nome_entrada"], a["cnpj"])
        except Exception:
            logger.warning(
                "Enriquecimento: falha ao salvar CNPJ/alias no banco (job %s).", job_id[:8], exc_info=True
            )

    # Audit trail: cada busca efetivamente feita à CNPJá consome créditos.
    from app.modules.consumo import repo as consumo_repo

    try:
        await consumo_repo.registrar_cnpj(
            escritorio_id=settings.escritorio_default_id, modulo="modulo01",
            operacao="enriquecimento", consultas=consumidos, contexto=f"job {job_id[:8]}",
        )
    except Exception:
        logger.warning(
            "Enriquecimento: falha ao registrar consumo do lote (job %s).", job_id[:8], exc_info=True
        )
