"""Endpoints do Módulo 01 — Análise de Crédito ICMS e Regularidade Fiscal.

Regra de organização: routers não contêm lógica de negócio, apenas validação
de entrada e orquestração de chamadas para os módulos em app/modules/modulo01/.
Os endpoints de progresso e relatório (CND/PDF) entram nas fases 3 e 5.
"""
import logging
import os
import re
import tempfile
from datetime import datetime

import httpx
from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile

from app.config import settings
from app.database import async_session_factory
from app.modules.consumo import repo as consumo_repo
from app.modules.modulo01 import (
    budget,
    cnd,
    cnpj_lookup,
    fornecedores_repo,
    pdf_generator,
    risk,
    service,
)
from app.modules.modulo01.jobs import store

logger = logging.getLogger("modulo01")


async def _casar_com_banco(fornecedores: list[dict]) -> None:
    """Preenche o CNPJ dos pendentes a partir do banco de fornecedores (grátis). Tolerante a falha."""
    try:
        async with async_session_factory() as session:
            for f in fornecedores:
                if not f.get("cnpj"):
                    fr = await fornecedores_repo.buscar_exato(session, f["nome_forn"])
                    if fr:
                        f["cnpj"] = fr.cnpj
                        f["cnpj_pendente"] = False
                        f["cnpj_confirmado"] = True
    except Exception:
        logger.warning("Casamento com o banco de fornecedores indisponível.", exc_info=True)


async def _salvar_no_banco(itens: list[tuple[str, str, str]]) -> None:
    """Persiste (cnpj, razao_social, origem) resolvidos para reuso futuro. Tolerante a falha."""
    try:
        async with async_session_factory() as session:
            for cnpj, razao, origem in itens:
                await fornecedores_repo.upsert(session, cnpj, razao, origem)
    except Exception:
        logger.warning("Não foi possível salvar fornecedor(es) no banco.", exc_info=True)
from app.modules.modulo01.parser import ParserError
from app.modules.modulo01.schemas import CnpjManualIn, ProcessarResponse
from app.ratelimit import limiter

router = APIRouter()

EXTENSOES_VALIDAS = (".xls", ".xlsx")
_MAX_BYTES = settings.max_upload_mb * 1024 * 1024
_CHUNK = 1024 * 1024


@router.get("/status")
async def status():
    """Health check específico do Módulo 01."""
    return {"modulo": "01", "nome": "Análise de Crédito Fiscal", "status": "ok"}


def _validar_extensao(arquivo: UploadFile) -> None:
    nome = (arquivo.filename or "").lower()
    if not nome.endswith(EXTENSOES_VALIDAS):
        raise HTTPException(
            status_code=400,
            detail=f"Arquivo '{arquivo.filename}' inválido. Envie um .xls ou .xlsx.",
        )


async def _salvar_temp(arquivo: UploadFile) -> str:
    # Sufixo restrito a uma whitelist (não confiar no filename do cliente).
    ext = os.path.splitext((arquivo.filename or "").lower())[1]
    sufixo = ext if ext in EXTENSOES_VALIDAS else ".xls"
    fd, caminho = tempfile.mkstemp(suffix=sufixo)
    # Leitura em chunks com teto rígido: aborta antes de estourar a memória.
    total = 0
    with os.fdopen(fd, "wb") as f:
        while True:
            chunk = await arquivo.read(_CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if total > _MAX_BYTES:
                f.close()
                os.remove(caminho)
                raise HTTPException(
                    status_code=413,
                    detail=f"Arquivo excede o limite de {settings.max_upload_mb} MB.",
                )
            f.write(chunk)
    return caminho


@router.post("/processar", response_model=ProcessarResponse)
@limiter.limit(settings.rate_limit_processar)
async def processar(
    request: Request,
    entradas: UploadFile = File(..., description="Livro de Entradas (XLS)"),
    cadastro: UploadFile | None = File(None, description="Cadastro de Fornecedores (XLS, opcional)"),
):
    """Recebe os arquivos, classifica os fornecedores e devolve o resultado + job_id."""
    _validar_extensao(entradas)
    if cadastro is not None:
        _validar_extensao(cadastro)

    entradas_path = None
    cadastro_path = None
    try:
        entradas_path = await _salvar_temp(entradas)
        cadastro_path = await _salvar_temp(cadastro) if cadastro is not None else None
        metadados, resumo, fornecedores = service.processar(entradas_path, cadastro_path)
    except HTTPException:
        raise
    except ParserError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Falha ao processar os arquivos. Verifique se o layout corresponde ao Livro de Entradas do ERP.",
        )
    finally:
        for caminho in (entradas_path, cadastro_path):
            if caminho and os.path.exists(caminho):
                os.remove(caminho)

    # Casa CNPJ a partir do banco de fornecedores (cache de análises anteriores, grátis).
    await _casar_com_banco(fornecedores)
    resumo["cnpj_pendentes"] = sum(1 for f in fornecedores if not f.get("cnpj"))
    resumo["cnpj_casados"] = sum(1 for f in fornecedores if f.get("cnpj"))

    job_id = store.criar(
        {
            "status": "parsed",
            "metadados": metadados,
            "resumo": resumo,
            "fornecedores": fornecedores,
        }
    )

    return ProcessarResponse(
        job_id=job_id, status="parsed", metadados=metadados, resumo=resumo, fornecedores=fornecedores
    )


@router.post("/enriquecer-cnpj/{job_id}")
@limiter.limit("3/minute")
async def enriquecer_cnpj(request: Request, job_id: str, limite: int | None = None):
    """Busca o CNPJ por razão social dos fornecedores pendentes de um job (consome créditos).

    Passo sob demanda e com teto (controle de custo): a classificação não consome
    créditos; só esta chamada consulta a API externa. Para no primeiro sinal de
    créditos esgotados, preservando o que já casou.
    """
    if not settings.cnpj_lookup_api_key:
        raise HTTPException(
            status_code=400,
            detail="Busca de CNPJ não configurada (CNPJ_LOOKUP_API_KEY ausente no servidor).",
        )

    job = store.obter(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job não encontrado ou expirado.")
    if budget.restante("cnpj") <= 0:
        raise HTTPException(status_code=429, detail="Teto diário de buscas de CNPJ atingido.")

    teto = max(1, min(limite or settings.cnpj_lookup_limite_padrao, settings.cnpj_lookup_limite_max))
    pendentes = [(f["cod_forn"], f["nome_forn"]) for f in job["fornecedores"] if not f.get("cnpj")][:teto]

    contagem = {"processados": 0, "confirmados": 0, "baixa_confianca": 0, "ambiguos": 0, "nao_encontrados": 0}
    erros_pontuais = 0
    creditos_esgotados = False
    teto_diario_atingido = False
    achados: dict[str, tuple[str, bool, str]] = {}  # cod_forn -> (cnpj, confirmado, nome_oficial)

    async with httpx.AsyncClient() as client:
        for cod_forn, nome in pendentes:
            if not budget.consumir("cnpj"):
                teto_diario_atingido = True
                break
            try:
                r = await cnpj_lookup.buscar_por_nome(nome, None, client)
            except cnpj_lookup.LookupError as exc:
                if "créditos" in str(exc) or "Limite" in str(exc):
                    creditos_esgotados = True
                    break
                erros_pontuais += 1
                continue
            contagem["processados"] += 1
            conf = r["confianca"]
            if conf in (cnpj_lookup.CONF_ALTA, cnpj_lookup.CONF_BAIXA):
                achados[cod_forn] = (r["cnpj"], conf == cnpj_lookup.CONF_ALTA, r.get("nome_oficial") or nome)
                contagem["confirmados" if conf == cnpj_lookup.CONF_ALTA else "baixa_confianca"] += 1
            elif conf == cnpj_lookup.CONF_AMBIGUO:
                contagem["ambiguos"] += 1
            else:
                contagem["nao_encontrados"] += 1

    def _aplicar(job: dict) -> None:
        for f in job["fornecedores"]:
            if f["cod_forn"] in achados:
                cnpj, confirmado, _ = achados[f["cod_forn"]]
                f["cnpj"] = cnpj
                f["cnpj_pendente"] = False
                f["cnpj_confirmado"] = confirmado

    store.mutar(job_id, _aplicar)
    # Salva os CNPJ resolvidos no banco para reuso futuro (sem reconsultar a API paga).
    await _salvar_no_banco([(cnpj, nome_of, "cnpja") for cnpj, _, nome_of in achados.values()])

    # Audit trail do consumo: cada busca efetivamente feita ao CNPJá consome créditos.
    try:
        await consumo_repo.registrar_cnpj(
            escritorio_id=settings.escritorio_default_id, modulo="modulo01",
            operacao="enriquecimento", consultas=contagem["processados"], contexto=f"job {job_id[:8]}",
        )
    except Exception:
        logger.warning("Falha ao registrar consumo do enriquecimento (job %s).", job_id[:8], exc_info=True)

    atual = store.obter(job_id)
    pendentes_restantes = sum(1 for f in atual["fornecedores"] if not f.get("cnpj")) if atual else 0
    return {
        "job_id": job_id,
        **contagem,
        "erros_pontuais": erros_pontuais,
        "creditos_esgotados": creditos_esgotados,
        "teto_diario_atingido": teto_diario_atingido,
        "pendentes_restantes": pendentes_restantes,
    }


@router.post("/consultar-cnd/{job_id}")
@limiter.limit("6/minute")
async def consultar_cnd_endpoint(request: Request, job_id: str, limite: int | None = None):
    """Inicia a consulta de CND (regularidade fiscal) em background para os fornecedores com CNPJ.

    Passo sob demanda e com teto (controle de custo). Acompanhe pelo /progresso/{job_id}.
    """
    if not settings.infosimples_token:
        raise HTTPException(
            status_code=400,
            detail="Consulta de CND não configurada (INFOSIMPLES_TOKEN ausente no servidor).",
        )
    if not store.existe(job_id):
        raise HTTPException(status_code=404, detail="Job não encontrado ou expirado.")
    if budget.restante("cnd") <= 0:
        raise HTTPException(status_code=429, detail="Teto diário de consultas de CND atingido.")

    teto = max(1, min(limite or settings.cnd_limite_padrao, settings.cnd_limite_max))
    res = cnd.iniciar_consulta_job(job_id, teto)
    if res["status"] == "nao_encontrado":
        raise HTTPException(status_code=404, detail="Job não encontrado ou expirado.")
    if res["status"] == "ja_em_andamento":
        raise HTTPException(status_code=409, detail="Já existe uma consulta de CND em andamento para este job.")
    return {
        "job_id": job_id,
        "status": "em_andamento",
        "total": res["total"],
        "total_com_cnpj": res["total_com_cnpj"],
    }


@router.get("/resultado/{job_id}", response_model=ProcessarResponse)
async def resultado_job(job_id: str):
    """Devolve o estado atual do job (fornecedores atualizados após CNPJ/CND)."""
    job = store.obter(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job não encontrado ou expirado.")

    fornecedores = job["fornecedores"]
    resumo = dict(job["resumo"])
    # Recalcula os contadores de CNPJ, que mudam após enriquecimento/edição manual.
    resumo["cnpj_pendentes"] = sum(1 for f in fornecedores if not f.get("cnpj"))
    resumo["cnpj_casados"] = sum(1 for f in fornecedores if f.get("cnpj"))
    return ProcessarResponse(
        job_id=job_id,
        status=job.get("status", "parsed"),
        metadados=job.get("metadados", {}),
        resumo=resumo,
        fornecedores=fornecedores,
    )


@router.get("/progresso/{job_id}")
async def progresso(job_id: str):
    """Estado da consulta de CND (para polling do frontend)."""
    job = store.obter(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job não encontrado ou expirado.")
    return job.get(
        "cnd_progresso",
        {"total": 0, "consultados": 0, "falhas": 0, "percentual": 0.0, "status": "nao_iniciado"},
    )


@router.get("/relatorio/{job_id}")
@limiter.limit("30/minute")
async def relatorio(request: Request, job_id: str):
    """Gera e devolve o relatório PDF do job (capa, sumário, tabelas por grupo)."""
    job = store.obter(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job não encontrado ou expirado.")

    try:
        pdf = pdf_generator.gerar_pdf(job)
    except Exception:
        import logging

        logging.getLogger("modulo01").exception("Falha ao gerar PDF")
        raise HTTPException(status_code=500, detail="Falha ao gerar o relatório PDF.")

    cliente = (job.get("metadados") or {}).get("cliente") or "cliente"
    slug = re.sub(r"[^A-Za-z0-9]+", "_", cliente).strip("_").lower() or "cliente"
    data = datetime.now().strftime("%Y%m%d")
    nome = f"relatorio_fiscal_{slug}_{data}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


@router.post("/cnpj-manual/{job_id}")
@limiter.limit("30/minute")
async def cnpj_manual(request: Request, job_id: str, body: CnpjManualIn):
    """Define manualmente a razão social e o CNPJ de um fornecedor (sem consumir créditos).

    Usado para os fornecedores que a busca automática não confirmou. Valida o dígito
    verificador do CNPJ e marca como confirmado (entrada do usuário).
    """
    job = store.obter(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job não encontrado ou expirado.")

    # Preserva letras (CNPJ alfanumérico a partir de 2026), valida o DV e normaliza.
    cnpj = re.sub(r"[^0-9A-Za-z]", "", body.cnpj).upper()
    if not cnpj_lookup.validar_cnpj(cnpj):
        raise HTTPException(status_code=422, detail="CNPJ inválido (dígito verificador não confere).")

    if not any(f["cod_forn"] == body.cod_forn for f in job["fornecedores"]):
        raise HTTPException(status_code=404, detail="Fornecedor não encontrado neste job.")

    def _aplicar(j: dict) -> None:
        for f in j["fornecedores"]:
            if f["cod_forn"] == body.cod_forn:
                f["cnpj"] = cnpj
                f["cnpj_pendente"] = False
                f["cnpj_confirmado"] = True
                f["cnpj_nao_casado"] = False
                if body.razao_social and body.razao_social.strip():
                    f["nome_forn"] = body.razao_social.strip()
                break
        # Se a CND já rodou, reaplica o risco para manter a consistência após a correção.
        if any(f.get("status_cnd") for f in j["fornecedores"]):
            risk.aplicar_risco(j["fornecedores"])

    store.mutar(job_id, _aplicar)
    atual = store.obter(job_id)
    final = next(f for f in atual["fornecedores"] if f["cod_forn"] == body.cod_forn)
    # Salva no banco para reuso futuro (correção manual vira conhecimento permanente).
    await _salvar_no_banco([(cnpj, final["nome_forn"], "manual")])
    return final


@router.get("/fornecedores/buscar")
@limiter.limit("60/minute")
async def buscar_fornecedores(request: Request, q: str = ""):
    """Busca gratuita no banco de fornecedores (cache local) por razão social."""
    try:
        async with async_session_factory() as session:
            forns = await fornecedores_repo.buscar(session, q)
    except Exception:
        raise HTTPException(status_code=503, detail="Busca de fornecedores temporariamente indisponível.")
    return {
        "resultados": [
            {"cnpj": f.cnpj, "razao_social": f.razao_social, "origem": f.origem} for f in forns
        ]
    }
