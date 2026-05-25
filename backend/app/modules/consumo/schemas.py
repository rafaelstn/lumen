"""Contratos de entrada/saída do módulo de consumo (Pydantic).

Valores monetários trafegam como INTEIRO em centavos (campos *_centavos). O frontend
formata para reais. Nunca float em dinheiro.
"""
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.modules.consumo.models import SERVICOS_VALIDOS


class SaldoServicoOut(BaseModel):
    servico: str
    creditos_comprados: int
    creditos_consumidos: int
    creditos_restantes: int
    valor_total_pago_centavos: int
    # Preço por crédito em centavos, como string decimal para preservar a fração (ex.: "2.499").
    preco_por_credito: str
    custo_restante_centavos: int


class SaldoOut(BaseModel):
    itens: list[SaldoServicoOut]


class RecargaIn(BaseModel):
    servico: str
    creditos: int = Field(gt=0, description="Créditos comprados neste pacote (> 0).")
    valor_total_centavos: int = Field(
        gt=0, description="Valor total pago pelo pacote, em centavos inteiros (> 0)."
    )

    @field_validator("servico")
    @classmethod
    def _servico_valido(cls, v: str) -> str:
        if v not in SERVICOS_VALIDOS:
            raise ValueError(f"servico deve ser um de {SERVICOS_VALIDOS}.")
        return v


class RecargaOut(BaseModel):
    servico: str
    creditos_comprados: int
    valor_total_pago_centavos: int
    # Preço por crédito derivado, string decimal (preserva fração, ex.: "2.499").
    preco_por_credito: str
    atualizado_em: datetime | None = None


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
