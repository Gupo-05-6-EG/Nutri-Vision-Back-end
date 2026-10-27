"""Ponto de entrada da API do Nutri Vision."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.observabilidade import RastreioMiddleware, configurar_logs


def create_app() -> FastAPI:
    settings = get_settings()
    configurar_logs(settings.LOG_LEVEL, settings.logs_em_json)

    app = FastAPI(
        title=settings.PROJECT_NAME,
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    )

    if settings.BACKEND_CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.BACKEND_CORS_ORIGINS,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Adicionado por ultimo = mais externo: mede e loga ate as respostas do CORS.
    app.add_middleware(RastreioMiddleware)

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {"service": settings.PROJECT_NAME, "docs": "/docs"}

    return app


app = create_app()
