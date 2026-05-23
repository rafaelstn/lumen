"""Modelos do Módulo 02 — Score Fiscal e monitoramento de fornecedores.

Todos carregam escritorio_id (multi-tenant desde o schema, conforme o roadmap),
mesmo que o MVP use só o escritório default. CND NÃO é cacheada como verdade —
o histórico registra cada consulta pontual com data, pois regularidade é volátil.
"""
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class FornecedorMonitorado(Base):
    __tablename__ = "fornecedores_monitorados"
    __table_args__ = (UniqueConstraint("escritorio_id", "cnpj", name="uq_monitorado_escritorio_cnpj"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    escritorio_id: Mapped[str] = mapped_column(String(36), index=True)
    cnpj: Mapped[str] = mapped_column(String(14), index=True)
    razao_social: Mapped[str | None] = mapped_column(String(255), default=None)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    score_atual: Mapped[int | None] = mapped_column(Integer, default=None)
    status_cnd_atual: Mapped[str | None] = mapped_column(String(30), default=None)
    ultima_consulta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HistoricoCnd(Base):
    __tablename__ = "historico_cnd"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    fornecedor_id: Mapped[str] = mapped_column(String(36), index=True)
    escritorio_id: Mapped[str] = mapped_column(String(36), index=True)
    status: Mapped[str] = mapped_column(String(30))  # NEGATIVA|POSITIVA|POSITIVA_EFEITO_NEGATIVA|FALHA
    score: Mapped[int | None] = mapped_column(Integer, default=None)
    detalhes: Mapped[dict | None] = mapped_column(JSON, default=None)
    consultado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Alerta(Base):
    __tablename__ = "alertas"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    escritorio_id: Mapped[str] = mapped_column(String(36), index=True)
    fornecedor_id: Mapped[str] = mapped_column(String(36), index=True)
    tipo: Mapped[str] = mapped_column(String(30))  # MUDANCA_STATUS|SCORE_CRITICO|DEVEDOR_CONTUMAZ
    mensagem: Mapped[str] = mapped_column(String(500))
    lido: Mapped[bool] = mapped_column(Boolean, default=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
