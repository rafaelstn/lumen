"""Configuração central da aplicação, carregada de variáveis de ambiente."""
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Segredos JWT proibidos quando a auth está ligada (placeholders de dev). Ligar o login com
# um destes permitiria a qualquer um forjar um token de admin: bloqueia o boot.
_JWT_SECRETS_PROIBIDOS = {"trocar-em-producao", "dev-secret", "change-me", "secret", ""}
_JWT_SECRET_MIN_LEN = 32


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
    cnpj_lookup_limite_padrao: int = 8  # teto de fornecedores por chamada (cabe sob o rate sem timeout de request)
    cnpj_lookup_limite_max: int = 200  # clamp do parâmetro 'limite' (anti-abuso)
    # Rate limit do plano CNPJá (req/min). O lote espaça as chamadas para não estourar 429.
    cnpj_rate_por_min: int = 10
    cnpj_rate_folga: float = 0.15  # folga sobre o intervalo mínimo (margem contra jitter de relógio)
    cnpj_retry_max: int = 2  # tentativas extras no 429 antes de desistir do lote
    cnpj_retry_backoff_s: float = 2.0  # backoff base do retry quando não há Retry-After
    cnpj_retry_backoff_teto_s: float = 8.0  # teto do espera por retry (não estourar o request HTTP)

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

    # Auth (JWT próprio). Flag MESTRE do login/multi-tenant. Com False (estado atual),
    # o sistema roda anônimo no escritório default, EXATAMENTE como hoje (sem exigir
    # Authorization). Com True, exige login e isola os dados por escritório. O Rafael
    # liga a flag depois que o frontend de login estiver pronto.
    auth_enabled: bool = False
    jwt_secret: str = "trocar-em-producao"
    jwt_algorithm: str = "HS256"
    jwt_expira_min: int = 480
    escritorio_default_id: str = "00000000-0000-0000-0000-000000000001"

    # Admin principal semeado no startup a partir do env (idempotente: só cria se não
    # existir um usuário com este e-mail). Em produção, setar no Railway com senha forte.
    admin_email: str = ""
    admin_password: str = ""
    # Tamanho mínimo de senha no signup (validação na borda).
    senha_min_len: int = 8

    # Limites de upload e do store de jobs (proteção contra DoS/OOM).
    max_upload_mb: int = 10
    max_linhas_planilha: int = 50000
    job_ttl_seconds: int = 3600
    job_cap: int = 200
    rate_limit_processar: str = "5/minute"

    @model_validator(mode="after")
    def _exige_jwt_secret_forte_com_auth(self) -> "Settings":
        """Com auth_enabled=True, o segredo do JWT não pode ser placeholder nem curto.

        A flag off mantém o comportamento atual (anônimo, sem JWT real), então não força nada.
        Ligar a auth com segredo fraco quebraria toda a confiança do token (forja de admin),
        por isso falhamos no boot em vez de rodar inseguro.
        """
        if self.auth_enabled:
            secret = (self.jwt_secret or "").strip()
            if secret.lower() in _JWT_SECRETS_PROIBIDOS or len(secret) < _JWT_SECRET_MIN_LEN:
                raise ValueError(
                    "JWT_SECRET inseguro: com AUTH_ENABLED=true, defina um segredo forte "
                    f"(>= {_JWT_SECRET_MIN_LEN} caracteres, não um placeholder)."
                )
            if self.jwt_algorithm.lower() == "none":
                raise ValueError("JWT_ALGORITHM 'none' é proibido (assinatura obrigatória).")
        return self

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
