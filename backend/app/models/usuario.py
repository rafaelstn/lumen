"""Usuário do sistema (login). Um login por escritório no início (dono do escritório).

Multi-tenant: cada Usuario pertence a um Escritorio (escritorio_id). O papel define a
visão: 'admin' enxerga TUDO de todos os escritórios; 'escritorio' só os dados do próprio.
A senha NUNCA é armazenada em texto: guardamos só o hash bcrypt (ver app/auth/security).
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

ROLE_ADMIN = "admin"
ROLE_ESCRITORIO = "escritorio"
ROLES_VALIDOS = (ROLE_ADMIN, ROLE_ESCRITORIO)


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    # Hash bcrypt da senha. NUNCA o texto puro. Não vaza em nenhuma resposta da API.
    senha_hash: Mapped[str] = mapped_column(String(255))
    escritorio_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("escritorios.id"), index=True
    )
    role: Mapped[str] = mapped_column(String(20), default=ROLE_ESCRITORIO)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
