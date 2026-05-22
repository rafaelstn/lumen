"""Modelos de resposta da API do Módulo 01."""
from pydantic import BaseModel


class FornecedorResult(BaseModel):
    cod_forn: str
    nome_forn: str
    cnpj: str | None = None
    cnpj_pendente: bool = True
    cnpj_nao_casado: bool = False
    cnpj_confirmado: bool = False
    grupo: str
    label: str
    verificar_st: bool = False
    tem_estorno: bool = False
    total_compras: float
    total_valor_icms: float
    aliquota_max: float
    aliquota_efetiva_pct: float
    credito_aproveitado: float
    credito_perdido: float
    n_lancamentos: int


class Resumo(BaseModel):
    total_fornecedores: int
    grupo_a: int
    grupo_b: int
    grupo_c: int
    grupo_indefinido: int = 0
    caso_especial: int
    total_credito_aproveitado: float
    total_compras_sem_credito: float
    cnpj_casados: int = 0
    cnpj_pendentes: int = 0


class ProcessarResponse(BaseModel):
    job_id: str
    status: str
    resumo: Resumo
    fornecedores: list[FornecedorResult]


class CnpjManualIn(BaseModel):
    cod_forn: str
    cnpj: str
    razao_social: str | None = None
