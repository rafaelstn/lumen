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
