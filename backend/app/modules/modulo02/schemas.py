"""DTOs do Módulo 02."""
from pydantic import BaseModel


class DueDiligenceIn(BaseModel):
    cnpjs: list[str]


class MonitorarIn(BaseModel):
    cnpj: str


class AvaliacaoOut(BaseModel):
    cnpj: str
    razao_social: str | None = None
    situacao_cadastral: str | None = None
    simples_optante: bool | None = None
    status_cnd: str
    score: int
    faixa: str
    componentes: dict


class MonitoradoOut(BaseModel):
    id: str
    cnpj: str
    razao_social: str | None = None
    score_atual: int | None = None
    status_cnd_atual: str | None = None
    ultima_consulta: str | None = None


class AlertaOut(BaseModel):
    id: str
    tipo: str
    mensagem: str
    lido: bool
    criado_em: str
