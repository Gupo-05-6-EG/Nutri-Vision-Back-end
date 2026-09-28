"""Configuracao da aplicacao, carregada de variaveis de ambiente / .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Aplicacao
    PROJECT_NAME: str = "Nutri Vision API"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # Banco de dados
    DATABASE_URL: str = "postgresql+psycopg://nutrivision:nutrivision@localhost:5432/nutrivision"
    TEST_DATABASE_URL: str = "sqlite+pysqlite:///:memory:"

    # Seguranca / JWT (Task 1.2)
    SECRET_KEY: str = "troque-esta-chave-em-producao"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 dias

    # CORS
    BACKEND_CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:8080",
    ]

    # Servico de IA (usado a partir da Task 3.1)
    AI_SERVICE_URL: str = "http://localhost:8001"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


@lru_cache
def get_settings() -> Settings:
    """Settings em cache - evita reler o .env em cada request."""
    return Settings()
