"""Modelo do banco de fornecedores: cache persistente e global de CNPJ ↔ razão social.

Guarda só a identidade (estável). A CND/regularidade NÃO é persistida aqui porque é
volátil — sempre consultada fresca. Reuso entre análises evita reconsultar API paga.
"""
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Fornecedor(Base):
    __tablename__ = "fornecedores"

    id: Mapped[int] = mapped_column(primary_key=True)
    cnpj: Mapped[str] = mapped_column(String(14), unique=True, index=True)
    razao_social: Mapped[str] = mapped_column(String(255))
    # Nome normalizado (uppercase, sem acento/pontuação) para casamento por razão social.
    nome_normalizado: Mapped[str] = mapped_column(String(255), index=True)
    origem: Mapped[str] = mapped_column(String(20), default="manual")  # manual | cnpja | importado
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
