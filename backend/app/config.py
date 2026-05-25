"""Configuração central da aplicação, carregada de variáveis de ambiente."""
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://fiscal_user:fiscal_pass@postgres:5432/fiscal_db"
    cors_origins: str = "http://localhost:3000"

    @field_validator("cors_origins")
    @classmethod
    def _rejeita_cors_curinga(cls, v: str) -> str:
        # Dado fiscal confidencial: nunca liberar CORS para qualquer origem.
        if "*" in v:
            raise ValueError("CORS_ORIGINS não pode conter '*' (dado fiscal confidencial).")
        return v

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

    # Lookup de CNPJ por nome / enriquecimento (CNPJá). Chave só via env, nunca no código.
    cnpj_lookup_provider: str = "cnpja"
    cnpj_lookup_base_url: str = "https://api.cnpja.com"
    cnpj_lookup_api_key: str = ""
    cnpj_lookup_limite_padrao: int = 20  # teto de fornecedores por chamada (controle de créditos)
    cnpj_lookup_limite_max: int = 200  # clamp do parâmetro 'limite' (anti-abuso)

    # Consulta de CND (regularidade fiscal) via Infosimples. Token só via env.
    cnd_provider: str = "infosimples"
    infosimples_base_url: str = "https://api.infosimples.com/api/v2/consultas"
    infosimples_token: str = ""
    infosimples_timeout: int = 120  # timeout da consulta na origem (Infosimples), em segundos
    cnd_limite_padrao: int = 20  # teto de fornecedores por chamada (controle de custo)
    cnd_limite_max: int = 200  # clamp do parâmetro 'limite' (anti-abuso)
    cnd_concorrencia: int = 4  # consultas CND simultâneas

    # Teto global diário de consultas pagas (blindagem de fatura, independe de IP).
    cnd_max_diario: int = 300
    cnpj_max_diario: int = 300

    # Monitoramento automático (APScheduler) do M02. Desligado por padrão: consome
    # consultas pagas todo dia. Ligar conscientemente (gasto recorrente). Reavaliação
    # manual via POST /api/modulo02/reavaliar sempre disponível.
    scheduler_enabled: bool = False
    scheduler_hora: int = 3  # hora do dia (0-23) para o monitoramento diário

    # Feature flags de módulo (roadmap). M02/M03 só ligam após o gate comercial do M01.
    # M03 (Recuperação de Créditos) CONGELADO em 2026-05-25: as teses exigem
    # SPED Contribuições/Fiscal (receita/saída) e hoje só temos o Livro de Entradas.
    # Spec preservada no vault: 01-Projects/Lumen-Fiscal/M03-Spec-Recuperacao-Creditos-CONGELADO.md
    modulo01_enabled: bool = True
    modulo02_enabled: bool = True
    modulo03_enabled: bool = False

    # Auth (JWT próprio) — preparado, NÃO ativo no MVP. O login real entra depois;
    # por ora todo dado pertence ao escritório default (single-tenant na prática).
    jwt_secret: str = "trocar-em-producao"
    jwt_algorithm: str = "HS256"
    jwt_expira_min: int = 480
    escritorio_default_id: str = "00000000-0000-0000-0000-000000000001"

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
