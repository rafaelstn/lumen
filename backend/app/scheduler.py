"""Monitoramento contínuo do M02 via APScheduler (não Celery, conforme roadmap).

Desligado por padrão (settings.scheduler_enabled) porque re-avaliar a carteira consome
consultas pagas diariamente. Quando ligado, re-avalia todos os escritórios na hora
configurada, respeitando o teto de orçamento. A reavaliação manual (endpoint) é sempre
disponível e dá controle fino de custo.
"""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings

logger = logging.getLogger("scheduler")
scheduler = AsyncIOScheduler()


async def _monitorar_todos() -> None:
    """Re-avalia a carteira de todos os escritórios (job diário)."""
    from sqlalchemy import select

    from app.database import async_session_factory
    from app.models.escritorio import Escritorio
    from app.modules.modulo02 import service

    async with async_session_factory() as session:
        ids = (await session.execute(select(Escritorio.id))).scalars().all()
    for escritorio_id in ids:
        try:
            async with async_session_factory() as session:
                resultado = await service.reavaliar_carteira(session, escritorio_id)
            logger.info("Monitoramento %s: %s", escritorio_id, resultado)
        except Exception:
            logger.exception("Falha no monitoramento do escritório %s", escritorio_id)


def iniciar() -> None:
    if not settings.scheduler_enabled:
        logger.info("Scheduler de monitoramento desligado (scheduler_enabled=False).")
        return
    scheduler.add_job(_monitorar_todos, "cron", hour=settings.scheduler_hora, minute=0, id="monitoramento_diario")
    scheduler.start()
    logger.info("Scheduler de monitoramento ligado (diário às %sh).", settings.scheduler_hora)
