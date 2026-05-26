"""Schemas de entrada/saída do auth. Validação na borda (Pydantic): nunca confiar no cliente."""
from pydantic import BaseModel, EmailStr, Field

from app.config import settings


class SignupIn(BaseModel):
    nome_escritorio: str = Field(min_length=2, max_length=255)
    email: EmailStr
    senha: str = Field(min_length=settings.senha_min_len, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    senha: str = Field(min_length=1, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expira_em_min: int


class UsuarioOut(BaseModel):
    """Dados do usuário SEM senha_hash (nunca vaza)."""

    id: str
    email: EmailStr
    escritorio_id: str
    role: str
    ativo: bool


class SignupOut(BaseModel):
    usuario: UsuarioOut
    token: TokenOut


class EscritorioOut(BaseModel):
    id: str
    nome: str
    total_usuarios: int
    criado_em: str | None = None


class CriarEscritorioIn(BaseModel):
    """Admin cria um escritório + usuário dono. Validação na borda; senha >= mínimo."""

    nome: str = Field(min_length=2, max_length=255)
    email: EmailStr
    senha: str = Field(min_length=settings.senha_min_len, max_length=128)


class EscritorioCriadoOut(BaseModel):
    """Resposta da criação admin: dados do escritório + e-mail do dono. SEM senha_hash."""

    id: str
    nome: str
    criado_em: str | None = None
    dono_usuario_id: str
    dono_email: EmailStr
    dono_role: str


class EscritorioRemovidoOut(BaseModel):
    """Resposta da remoção: id, status e as contagens do que foi apagado por tabela."""

    id: str
    status: str = "removido"
    removidos: dict[str, int] = {}


# --- Dashboard admin (visão sistêmica) ---------------------------------------------
# Dinheiro SEMPRE em centavos inteiros. Nenhum dado pessoal (sócios) entra aqui.


class ConsumoAgg(BaseModel):
    """Consumo agregado: créditos e custo (centavos)."""

    creditos_consumidos: int = 0
    custo_centavos: int = 0


class ConsumoPeriodoOut(BaseModel):
    """Recorte de consumo de um período (datas opcionais; None = sem limite)."""

    inicio: str | None = None
    fim: str | None = None
    consultas_pagas: int = 0
    creditos_consumidos: int = 0
    custo_centavos: int = 0


class ResumoAdminOut(BaseModel):
    """Métricas gerais do sistema para o dashboard admin."""

    total_escritorios: int
    total_usuarios: int
    total_analises: int
    fornecedores_cache_global: int
    fornecedores_cadastro_completo: int
    consultas_pagas: int
    creditos_consumidos: int
    custo_total_centavos: int
    consumo_periodo: ConsumoPeriodoOut


class EscritorioMetricasOut(BaseModel):
    """Item da lista admin de escritórios, com agregações."""

    id: str
    nome: str
    criado_em: str | None = None
    total_usuarios: int = 0
    total_analises: int = 0
    total_fornecedores_pesquisados: int = 0
    consumo: ConsumoAgg
    ultima_atividade: str | None = None


class ServicoConsumoOut(BaseModel):
    consultas: int = 0
    creditos_consumidos: int = 0
    custo_centavos: int = 0


class ConsumoEscritorioOut(BaseModel):
    """Consumo de um escritório no período, com quebra por serviço."""

    escritorio_id: str
    nome: str
    creditos_consumidos: int = 0
    custo_centavos: int = 0
    por_servico: dict[str, ServicoConsumoOut] = {}


class UsuarioResumoOut(BaseModel):
    """Usuário no detalhe do escritório. SEM senha_hash, nunca."""

    id: str
    email: EmailStr
    role: str
    ativo: bool
    criado_em: str | None = None


class ConsumoDetalheOut(BaseModel):
    creditos_consumidos: int = 0
    custo_centavos: int = 0
    por_servico: dict[str, ServicoConsumoOut] = {}


class EscritorioDetalheOut(BaseModel):
    """Detalhe de um escritório para o admin."""

    id: str
    nome: str
    criado_em: str | None = None
    usuarios: list[UsuarioResumoOut] = []
    total_analises: int = 0
    total_fornecedores_pesquisados: int = 0
    consumo: ConsumoDetalheOut
