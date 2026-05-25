"""Contratos de entrada/saída do módulo de consumo (Pydantic).

Valores monetários trafegam como INTEIRO em centavos (campos *_centavos). O frontend
formata para reais. Nunca float em dinheiro.
"""
from datetime import datetime

from pydantic import BaseModel


class HistoricoItemOut(BaseModel):
    id: str
    criado_em: datetime
    modulo: str
    servico: str
    operacao: str
    quantidade: int
    creditos_consumidos: int
    preco_unitario_centavos: int
    custo_centavos: int
    consumo_estimado: bool
    contexto: str | None = None


class TotaisOut(BaseModel):
    creditos_consumidos: int
    custo_centavos: int


class PeriodoOut(BaseModel):
    periodo: str  # "YYYY-MM-DD" (dia) ou "YYYY-MM" (mês)
    creditos_consumidos: int
    custo_centavos: int


class HistoricoOut(BaseModel):
    itens: list[HistoricoItemOut]
    totais: TotaisOut
    por_dia: list[PeriodoOut]
    por_mes: list[PeriodoOut]
