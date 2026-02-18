from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "Starter Kit LLM Planner + Tool Plugins"
    ENV: str = Field(default="dev", description="dev|prod")
    DEBUG: bool = Field(default=True)

    # API
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Security
    INTERNAL_API_KEY: str = Field(default="", description="Required for internal endpoints like /wa/agent")

    WEBHOOK_VERIFY_SIGNATURE: bool = Field(default=False)
    WEBHOOK_SECRET: str = Field(default="", description="HMAC secret for provider webhook signature validation")
    WEBHOOK_REPLAY_WINDOW_SEC: int = Field(default=300, description="Anti-replay window seconds")

    # LLM - Ollama Cloud connector
    OLLAMA_API_BASE: str = Field(default="https://ollama.com/api")
    OLLAMA_API_KEY: str = Field(default="")
    OLLAMA_MODEL: str = Field(default="gpt-oss:120b")
    OLLAMA_TIMEOUT_SEC: int = Field(default=30)
    OLLAMA_RETRIES: int = Field(default=2)

    # Agent behavior
    ENABLE_ANSWERER: bool = Field(default=True)
    EXPOSE_DEBUG: bool = Field(default=True, description="Return debug payloads in dev")

    # Plugins
    TOOLS_PROVIDER: str = Field(default="app.plugins.tools_provider:provide_tools")  # ✅ CAMBIO
    QUERIES_PROVIDER: str = Field(default="app.plugins.queries_mock:register")

    # Dedupe/session
    DEDUPE_TTL_SEC: int = Field(default=3600)
    SESSION_TTL_SEC: int = Field(default=86400)

    CONFIRMATION_TTL_SEC: int = 1800  # 30 minutos (ej)

    # DB (MySQL - XAMPP)
    DB_HOST: str = Field(default="127.0.0.1")
    DB_PORT: int = Field(default=3306)
    DB_NAME: str = Field(default="app_db")
    DB_USER: str = Field(default="app_user")
    DB_PASS: str = Field(default="app_pass")

    DATABASE_URL: str | None = Field(default=None)

    # Rate limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_IP_MAX: int = 60
    RATE_LIMIT_IP_WINDOW_SEC: int = 60
    RATE_LIMIT_SESSION_MAX: int = 30
    RATE_LIMIT_SESSION_WINDOW_SEC: int = 60

    # SMTP (email)
    SMTP_HOST: str = Field(default="")
    SMTP_PORT: int = Field(default=587)
    SMTP_USER: str = Field(default="")
    SMTP_PASSWORD: str = Field(default="")
    SMTP_FROM: str = Field(default="")


settings = Settings()