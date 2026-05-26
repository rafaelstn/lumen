"""DTOs do Módulo 02."""
from pydantic import BaseModel


class DueDiligenceIn(BaseModel):
    cnpjs: list[str]
    # Quando False, avalia só o cadastro (CNPJá), sem consultar a CND (Infosimples). Mais
    # barato (~R$0,05 vs ~R$0,31) e não depende da Receita estar no ar. Score fica parcial.
    incluir_cnd: bool = True


class MonitorarIn(BaseModel):
    cnpj: str


class AvaliacaoOut(BaseModel):
    cnpj: str
    razao_social: str | None = None
    situacao_cadastral: str | None = None
    simples_optante: bool | None = None
    status_cnd: str | None = None  # None = CND não consultada (incluir_cnd=False)
    origem_fora: bool = False      # True = CND falhou por a Receita/PGFN estar fora do ar
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
