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

    # Criptografia de dados sensiveis em repouso (Task 1.6). Chave Fernet. Em
    # producao, gere uma propria e guarde fora do repositorio:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    ENCRYPTION_KEY: str = "khW5PwcdjqnkKxVIr6dlJXX7i2qQv3HH656bD9NcTsU="

    # HTTPS (Task 1.6): com True, redireciona http -> https e envia HSTS. Ligar em
    # producao (atras de proxy, o proxy tem que mandar X-Forwarded-Proto).
    HTTPS_ONLY: bool = False

    # Fuso oficial: recorte do "dia" de consumo, semana do ranking, lembretes (B5)
    APP_TIMEZONE: str = "America/Sao_Paulo"

    # Vinculacao paciente-nutricionista (Task 1.4)
    LINKING_CODE_EXPIRE_MINUTES: int = 60 * 24

    # Logs (Task 7.1). LOG_JSON sem valor = JSON so em producao.
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool | None = None

    # CORS
    BACKEND_CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:8080",
    ]

    # Servico de IA (Nutri-Vision-IA): analise de fotos de refeicoes
    AI_SERVICE_URL: str = "http://localhost:8001"
    # Tempo maximo de cada chamada ao servico de IA (envio da foto ou consulta)
    AI_SERVICE_TIMEOUT_S: float = 30.0
    # Mesmo limite de upload do servico de IA (10 MB)
    AI_MAX_UPLOAD_BYTES: int = 10 * 1024 * 1024

    # Push via Firebase Cloud Messaging (Task 2.8): caminho do JSON da conta de servico.
    FCM_CREDENTIALS_FILE: str | None = None

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def logs_em_json(self) -> bool:
        return self.is_production if self.LOG_JSON is None else self.LOG_JSON


@lru_cache
def get_settings() -> Settings:
    """Settings em cache - evita reler o .env em cada request."""
    return Settings()
