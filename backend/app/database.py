"""Configuração do banco (SQLAlchemy async). Estrutura criada agora, usada nos módulos futuros."""
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False, future=True)

async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncSession:
    """Dependency do FastAPI para obter uma sessão de banco por request."""
    async with async_session_factory() as session:
        yield session
