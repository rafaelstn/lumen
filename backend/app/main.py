import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.ratelimit import limiter
from app.routers import modulo01, modulo02


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Cria as tabelas e semeia o escritório default. Tolerante: se o DB estiver
    # indisponível, loga e segue (recursos que dependem do banco apenas não funcionam).
    try:
        from app.database import async_session_factory, engine
        from app.models import escritorio, fornecedor  # noqa: F401 — registra no metadata
        from app.models.base import Base
        from app.models.escritorio import Escritorio
        from app.modules.modulo02 import models as _m02  # noqa: F401 — registra no metadata

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

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


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
