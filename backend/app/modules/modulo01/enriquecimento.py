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


def _escritorio_do_job(job: dict | None) -> str:
    """Tenant dono do job. Fallback no default quando a flag de auth está desligada."""
    return (job or {}).get("escritorio_id") or settings.escritorio_default_id


def _pendentes_brutos(job: dict) -> list[tuple[str, str]]:
    """(cod_forn, nome_forn) dos fornecedores do job sem CNPJ (candidatos a enriquecer)."""
    return [(f["cod_forn"], f["nome_forn"]) for f in job["fornecedores"] if not f.get("cnpj")]


async def separar_pendentes(job_id: str) -> dict:
    """Separa os pendentes do job em NOVOS (nunca tentados) e JÁ TENTADOS sem sucesso.

    Consulta enriquecimento_tentativa pelo escritório dono do job. Tolerante a falha de banco:
    se a consulta cair, considera todos como novos (não bloqueia o fluxo, só não economiza).

    Retorna {total_pendentes, novos, ja_tentados} (contagens) — contrato do endpoint de
    pendentes, para o frontend decidir o texto do botão e a estimativa de custo.
    """
    job = store.obter(job_id)
    if job is None:
        return {"total_pendentes": 0, "novos": 0, "ja_tentados": 0}
    brutos = _pendentes_brutos(job)
    ja = await _nomes_ja_tentados(_escritorio_do_job(job))
    novos = sum(1 for _cod, nome in brutos if cnpj_lookup._normalizar(nome) not in ja)
    total = len(brutos)
    return {"total_pendentes": total, "novos": novos, "ja_tentados": total - novos}


async def _nomes_ja_tentados(escritorio_id: str) -> set[str]:
    """Lê do banco os nomes normalizados já tentados sem sucesso. Tolerante: erro -> set vazio."""
    try:
        async with async_session_factory() as session:
            return await fornecedores_repo.nomes_ja_tentados(session, escritorio_id)
    except Exception:
        logger.warning(
            "Enriquecimento: não foi possível ler a lista de já-tentados (segue sem pular).",
            exc_info=True,
        )
        return set()


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


async def iniciar_enriquecimento_job(job_id: str, limite: int, forcar: bool = False) -> dict:
    """Inicia o enriquecimento de CNPJ em background. Idempotente: não dispara se já em andamento.

    `limite` é o teto de segurança por job (clamp em cnpj_lookup_limite_max). Processa os
    pendentes (sem CNPJ) até esse teto.

    `forcar=False` (default): PULA os nomes já tentados sem sucesso por este escritório
    (não queima crédito repesquisando o que já não achou). `forcar=True`: re-inclui os
    já-tentados (ex.: usuário subiu arquivo novo e quer tentar de novo).

    Retorna {status: iniciado|ja_em_andamento|nao_encontrado, total}.
    """
    # Lê a lista de já-tentados FORA do lock do store (operação async de banco). Com forcar,
    # nem consulta: vai processar todos os pendentes de novo.
    job = store.obter(job_id)
    if job is None:
        return {"status": "nao_encontrado"}
    ja_tentados: set[str] = set() if forcar else await _nomes_ja_tentados(_escritorio_do_job(job))

    info: dict = {}

    def _preparar(job: dict) -> None:
        prog = job.get("enriquecimento_progresso")
        if prog and prog.get("status") == "em_andamento":
            info["status"] = "ja_em_andamento"
            return
        pendentes = [
            (cod, nome)
            for cod, nome in _pendentes_brutos(job)
            if forcar or cnpj_lookup._normalizar(nome) not in ja_tentados
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


def _classificar(
    prog: dict, achados: dict, nao_achados: dict, cod_forn: str, nome: str, r: dict
) -> None:
    """Atualiza as contagens do progresso e registra o achado confirmável. Sob o lock do store.

    `achados` acumula os confirmáveis (viram Fornecedor/alias). `nao_achados` acumula os que
    deram nao_encontrado/ambiguo (viram registro em enriquecimento_tentativa, para pular no
    próximo enriquecimento): cod_forn -> (nome_entrada, resultado).
    """
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
        nao_achados[cod_forn] = (nome, cnpj_lookup.CONF_AMBIGUO)
    else:
        prog["nao_encontrados"] += 1
        nao_achados[cod_forn] = (nome, cnpj_lookup.CONF_NAO_ENCONTRADO)


async def _processar(job_id: str, pendentes: list[tuple[str, str]]) -> None:
    """Task de background: busca cada pendente sob throttle, aplica e persiste incrementalmente."""
    total = len(pendentes)
    throttle = cnpj_lookup.novo_throttle()
    # cod_forn -> (cnpj, confirmado, nome_oficial, nome_entrada); acumula para persistir ao fim.
    achados: dict[str, tuple[str, bool, str, str]] = {}
    # cod_forn -> (nome_entrada, resultado) dos nao_encontrado/ambiguo; vira tentativa registrada.
    nao_achados: dict[str, tuple[str, str]] = {}
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
                _classificar(prog, achados, nao_achados, _cod, _nome, _r)
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

    await _persistir(job_id, achados, nao_achados, consumidos)

    # Mantém o histórico em sincronia com o estado pós-enriquecimento (CNPJ casados).
    await _sincronizar_historico(job_id)


async def _persistir(job_id: str, achados: dict, nao_achados: dict, consumidos: int) -> None:
    """Salva os CNPJ resolvidos + aliases, registra os não-achados e o audit trail. Tolerante a falha.

    O dado essencial (CNPJ casado) já está no store; falha de banco/consumo não derruba o lote.
    `nao_achados` (nao_encontrado/ambiguo) vira tentativa registrada por escritório, para o
    próximo enriquecimento PULAR esses nomes e não queimar crédito.
    """
    # Tenant dono do job (multi-tenant). Fallback no default preserva o comportamento atual
    # quando a flag de auth está desligada (o job carrega o escritório default).
    job = store.obter(job_id) or {}
    escritorio_id = job.get("escritorio_id") or settings.escritorio_default_id

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
                    # Visão isolada do cache global: associa o CNPJ resolvido ao escritório.
                    await fornecedores_repo.associar_escritorio(session, escritorio_id, a["cnpj"])
        except Exception:
            logger.warning(
                "Enriquecimento: falha ao salvar CNPJ/alias no banco (job %s).", job_id[:8], exc_info=True
            )

    # Registra as tentativas SEM sucesso (nao_encontrado/ambiguo) por escritório. Idempotente:
    # se o nome já tinha registro, incrementa tentativas. É o que faz o próximo enriquecimento
    # pular esses nomes (sem queimar crédito). Tolerante: falha aqui não derruba o lote.
    if nao_achados:
        try:
            async with async_session_factory() as session:
                for nome_entrada, resultado in nao_achados.values():
                    await fornecedores_repo.registrar_tentativa(
                        session, escritorio_id, nome_entrada, resultado
                    )
        except Exception:
            logger.warning(
                "Enriquecimento: falha ao registrar tentativas sem sucesso (job %s).",
                job_id[:8], exc_info=True,
            )

    # Audit trail: cada busca efetivamente feita à CNPJá consome créditos.
    from app.modules.consumo import repo as consumo_repo

    try:
        await consumo_repo.registrar_cnpj(
            escritorio_id=escritorio_id, modulo="modulo01",
            operacao="enriquecimento", consultas=consumidos, contexto=f"job {job_id[:8]}",
        )
    except Exception:
        logger.warning(
            "Enriquecimento: falha ao registrar consumo do lote (job %s).", job_id[:8], exc_info=True
        )
