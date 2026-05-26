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
    status_cnd: str | None = None
    cnd_descricao: str | None = None
    # Dados completos da certidão (preenchidos no sucesso da consulta da vez).
    cnd_tipo: str | None = None              # texto/tipo da certidão (campo `certidao` da fonte)
    cnd_certidao_codigo: str | None = None   # código de controle (ex.: "078A.05F6.FFC6.C668")
    cnd_emissao_data: str | None = None      # data de emissão ("DD/MM/AAAA")
    cnd_validade: str | None = None          # validade da certidão ("DD/MM/AAAA")
    cnd_consulta_datahora: str | None = None # data/hora da consulta na fonte
    cnd_debitos_rfb: bool | None = None      # há débito na Receita Federal
    cnd_debitos_pgfn: bool | None = None     # há débito na Dívida Ativa/PGFN
    cnd_comprovante_url: str | None = None   # link do PDF oficial (null sem ignore_site_receipt)
    cnd_falha_motivo: str | None = None      # motivo legível quando status_cnd == FALHA
    # Metadado de controle da última CND consultada deste CNPJ (vem do banco ao casar).
    # Informativo: o frontend mostra "CND consultada em X, estava Y" antes de repuxar.
    # NÃO substitui status_cnd (volátil, da consulta da vez) nem dispara reconsulta automática.
    cnd_ultima_consulta: str | None = None
    cnd_status_cache: str | None = None
    risco_2027: str | None = None
    motivo_risco: str | None = None
    impacto_financeiro_anual: float | None = None
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


class Metadados(BaseModel):
    cliente: str | None = None
    cnpj_cliente: str | None = None
    periodo: str | None = None


class ProcessarResponse(BaseModel):
    job_id: str
    status: str
    metadados: Metadados
    resumo: Resumo
    fornecedores: list[FornecedorResult]


class CnpjManualIn(BaseModel):
    cod_forn: str
    cnpj: str
    razao_social: str | None = None


class AnaliseHistoricoItem(BaseModel):
    """Item leve do histórico (sem o payload de fornecedores)."""

    id: str
    cliente: str | None = None
    cnpj_cliente: str | None = None
    periodo: str | None = None
    total_fornecedores: int = 0
    criado_em: str | None = None
    atualizado_em: str | None = None


class AnalisesHistoricoResponse(BaseModel):
    analises: list[AnaliseHistoricoItem]


class FornecedorGlobalItem(BaseModel):
    """Item da listagem global de fornecedores. NUNCA inclui sócios (LGPD)."""

    cnpj: str
    razao_social: str
    nome_fantasia: str | None = None
    municipio: str | None = None
    uf: str | None = None
    cnae_principal_descricao: str | None = None
    situacao_cadastral: str | None = None
    telefone_principal: str | None = None
    email_principal: str | None = None
    cadastro_atualizado_em: str | None = None
    cnd_ultima_consulta: str | None = None
    cnd_status_cache: str | None = None


class FornecedoresGlobaisResponse(BaseModel):
    total: int
    offset: int
    limit: int
    resultados: list[FornecedorGlobalItem]
