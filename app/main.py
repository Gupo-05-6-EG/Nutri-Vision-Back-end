"""Ponto de entrada da API do Nutri Vision."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware

from app.api.router import api_router
from app.core.config import get_settings

# Um ano. Diz ao navegador/cliente para usar so HTTPS neste dominio.
HSTS = "max-age=31536000; includeSubDomains"


def create_app() -> FastAPI:
    settings = get_settings()

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

    if settings.HTTPS_ONLY:
        # Ordem importa: o ultimo middleware adicionado roda primeiro, entao o
        # redirect decide antes de qualquer outra coisa e o HSTS entra na resposta.
        @app.middleware("http")
        async def _hsts(request: Request, call_next):  # type: ignore[no-untyped-def]
            resposta = await call_next(request)
            resposta.headers["Strict-Transport-Security"] = HSTS
            return resposta

        app.add_middleware(HTTPSRedirectMiddleware)

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {"service": settings.PROJECT_NAME, "docs": "/docs"}

    return app


app = create_app()
