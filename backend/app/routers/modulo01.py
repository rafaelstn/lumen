"""Endpoints do Módulo 01 — Análise de Crédito ICMS e Regularidade Fiscal.

Regra de organização: routers não contêm lógica de negócio, apenas validação
de entrada e orquestração de chamadas para os módulos em app/modules/modulo01/.
Os endpoints de progresso e relatório (CND/PDF) entram nas fases 3 e 5.
"""
import os
import tempfile

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from app.config import settings
from app.modules.modulo01 import service
from app.modules.modulo01.jobs import store
from app.modules.modulo01.parser import ParserError
from app.modules.modulo01.schemas import ProcessarResponse
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
        resumo, fornecedores = service.processar(entradas_path, cadastro_path)
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

    job_id = store.criar(
        {
            "status": "parsed",
            "resumo": resumo,
            "fornecedores": fornecedores,
        }
    )

    return ProcessarResponse(
        job_id=job_id, status="parsed", resumo=resumo, fornecedores=fornecedores
    )
