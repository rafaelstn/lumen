"""Tenant (escritório contábil). MVP: existe só o escritório default (single-tenant).

Quando o login for ativado, cada escritório vira um tenant real com seus usuários;
os models já carregam escritorio_id, então não há migration de dados.
"""
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Escritorio(Base):
    __tablename__ = "escritorios"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    nome: Mapped[str] = mapped_column(String(255), default="Escritório padrão")
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
