import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.ratelimit import limiter
from app.routers import consumo, modulo01, modulo02


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Cria as tabelas e semeia o escritório default. Tolerante: se o DB estiver
    # indisponível, loga e segue (recursos que dependem do banco apenas não funcionam).
    try:
        from app.database import async_session_factory, engine
        from app.models import escritorio, fornecedor  # noqa: F401 — registra no metadata
        from app.models.base import Base
        from app.models.escritorio import Escritorio
        from app.modules.consumo import models as _consumo  # noqa: F401 — registra no metadata
        from app.modules.modulo02 import models as _m02  # noqa: F401 — registra no metadata

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # Micro-migração idempotente: create_all NÃO adiciona colunas a tabelas
            # que já existem. Tabelas que ganharam colunas depois de já estarem em
            # produção precisam de ALTER. Só no Postgres (em teste o SQLite é recriado);
            # IF NOT EXISTS garante idempotência e não quebra em re-deploy.
            if conn.dialect.name == "postgresql":
                # Colunas adicionadas após a tabela já estar em produção. IF NOT EXISTS
                # garante idempotência em re-deploy. fornecedor_socios é tabela nova:
                # create_all a cria, não precisa de ALTER.
                _colunas_fornecedores = (
                    "cnd_ultima_consulta TIMESTAMPTZ NULL",
                    "cnd_ultimo_status VARCHAR(40) NULL",
                    "nome_fantasia VARCHAR(255) NULL",
                    "logradouro VARCHAR(255) NULL",
                    "numero VARCHAR(20) NULL",
                    "complemento VARCHAR(255) NULL",
                    "bairro VARCHAR(255) NULL",
                    "municipio VARCHAR(255) NULL",
                    "uf VARCHAR(2) NULL",
                    "cep VARCHAR(8) NULL",
                    "telefone_principal VARCHAR(20) NULL",
                    "email_principal VARCHAR(255) NULL",
                    "contatos JSON NULL",
                    "cnae_principal_codigo VARCHAR(10) NULL",
                    "cnae_principal_descricao VARCHAR(255) NULL",
                    "cnaes_secundarios JSON NULL",
                    "porte VARCHAR(40) NULL",
                    "natureza_juridica VARCHAR(255) NULL",
                    "situacao_cadastral VARCHAR(40) NULL",
                    "data_abertura VARCHAR(10) NULL",
                    "capital_social_centavos NUMERIC(18,0) NULL",
                    "cadastro_atualizado_em TIMESTAMPTZ NULL",
                )
                for coluna in _colunas_fornecedores:
                    await conn.exec_driver_sql(
                        f"ALTER TABLE fornecedores ADD COLUMN IF NOT EXISTS {coluna}"
                    )

        async with async_session_factory() as session:
            if await session.get(Escritorio, settings.escritorio_default_id) is None:
                session.add(Escritorio(id=settings.escritorio_default_id, nome="Escritório padrão"))
                await session.commit()
    except Exception:
        logging.getLogger("startup").exception("Não foi possível criar/verificar as tabelas.")

    try:
        from app.scheduler import iniciar as iniciar_scheduler

        iniciar_scheduler()  # inerte se scheduler_enabled=False
    except Exception:
        logging.getLogger("startup").exception("Não foi possível iniciar o scheduler.")
    yield


app = FastAPI(title="Sistema de Análise Fiscal", version="1.0.0", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(modulo01.router, prefix="/api/modulo01", tags=["Módulo 01"])
if settings.modulo02_enabled:
    app.include_router(modulo02.router, prefix="/api/modulo02", tags=["Módulo 02"])
app.include_router(consumo.router, prefix="/api/consultas", tags=["Consumo de APIs pagas"])


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
