from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import modulo01

app = FastAPI(title="Sistema de Análise Fiscal", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(modulo01.router, prefix="/api/modulo01", tags=["Módulo 01"])


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
