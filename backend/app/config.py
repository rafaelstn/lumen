"""Configuração central da aplicação, carregada de variáveis de ambiente."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://fiscal_user:fiscal_pass@postgres:5432/fiscal_db"
    cors_origins: str = "http://localhost:3000"

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
