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

    jobs_dir: str = "/app/_jobs"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
