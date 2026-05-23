import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.ratelimit import limiter
from app.routers import modulo01


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Cria a tabela do banco de fornecedores. Tolerante: se o DB estiver indisponível,
    # loga e segue (a app funciona sem o cache; o casamento por banco apenas não ocorre).
    try:
        from app.database import engine
        from app.models import fornecedor  # noqa: F401 — registra o modelo no metadata
        from app.models.base import Base

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception:
        logging.getLogger("startup").exception("Não foi possível criar/verificar as tabelas.")
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


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
