"""Configuração central da aplicação, carregada de variáveis de ambiente."""
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://fiscal_user:fiscal_pass@postgres:5432/fiscal_db"
    cors_origins: str = "http://localhost:3000"

    @field_validator("database_url")
    @classmethod
    def _force_asyncpg_driver(cls, v: str) -> str:
        # O Postgres gerenciado (ex.: Railway) entrega "postgresql://...".
        # O SQLAlchemy async exige o driver explícito "postgresql+asyncpg://...".
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        return v

    # Consulta CND
    cnd_portal_url: str = (
        "https://solucoes.receita.fazenda.gov.br/Servicos/certidaointernet/PJ/Emitir"
    )
    cnd_delay_min: float = 3.0
    cnd_delay_max: float = 8.0
    cnd_max_retries: int = 3

    # Solver de captcha
    captcha_provider: str = "2captcha"
    captcha_api_key: str = ""

    # Lookup de CNPJ por nome / enriquecimento (CNPJá). Chave só via env, nunca no código.
    cnpj_lookup_provider: str = "cnpja"
    cnpj_lookup_base_url: str = "https://api.cnpja.com"
    cnpj_lookup_api_key: str = ""
    cnpj_lookup_limite_padrao: int = 20  # teto de fornecedores por chamada (controle de créditos)

    # Consulta de CND (regularidade fiscal) via Infosimples. Token só via env.
    cnd_provider: str = "infosimples"
    infosimples_base_url: str = "https://api.infosimples.com/api/v2/consultas"
    infosimples_token: str = ""
    infosimples_timeout: int = 120  # timeout da consulta na origem (Infosimples), em segundos
    cnd_limite_padrao: int = 20  # teto de fornecedores por chamada (controle de custo)
    cnd_concorrencia: int = 4  # consultas CND simultâneas

    jobs_dir: str = "/app/_jobs"

    # Limites de upload e do store de jobs (proteção contra DoS/OOM).
    max_upload_mb: int = 10
    max_linhas_planilha: int = 50000
    job_ttl_seconds: int = 3600
    job_cap: int = 200
    rate_limit_processar: str = "5/minute"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
