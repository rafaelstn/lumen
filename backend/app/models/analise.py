"""Histórico de análises do Módulo 01: persiste o estado completo para reabrir sem re-subir a planilha.

O job em memória (JobStore) é volátil (TTL ~1h, some quando o usuário troca de tela). Esta tabela
guarda o ESTADO COMPLETO da análise (fornecedores + resumo + metadados) em JSON, para o usuário
reabrir a qualquer momento e continuar enriquecimento/CND de onde parou (re-hidratando o job).

É dado fiscal do cliente: fica no banco do projeto, vinculado ao escritório (single-tenant no MVP,
mas o escritorio_id já está presente para o multi-tenant futuro). O id é estável e igual ao job_id
da análise: reprocessar/atualizar a mesma análise é idempotente (upsert por id, nunca duplica).

LGPD: o JSON `dados` é o resultado da análise do próprio cliente (fornecedores que ele comprou),
não o quadro societário de terceiros — esse continua só em FornecedorSocio, sob demanda.
"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Analise(Base):
    __tablename__ = "analises"

    # id estável = job_id da análise. Upsert por id garante idempotência (reprocessar não duplica).
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # Tenant. Default = escritório único do MVP; já presente para o multi-tenant futuro.
    escritorio_id: Mapped[str] = mapped_column(String(36), index=True)

    # Identidade da análise (extraída dos metadados), desnormalizada para listar sem abrir o JSON.
    cliente: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cnpj_cliente: Mapped[str | None] = mapped_column(String(20), nullable=True)
    periodo: Mapped[str | None] = mapped_column(String(40), nullable=True)
    total_fornecedores: Mapped[int] = mapped_column(Integer, default=0)

    # ESTADO COMPLETO da análise para reabrir: {"fornecedores": [...], "resumo": {...},
    # "metadados": {...}}. É o mesmo payload que /resultado/{job_id} devolve (menos o job_id,
    # que é o próprio id). Mantido em sincronia após enriquecimento de CNPJ e CND/risco.
    dados: Mapped[dict] = mapped_column(JSON)

    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
