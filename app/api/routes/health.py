"""Endpoints de healthcheck (RNF09 - monitoramento)."""

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import get_settings
from app.db.deps import DbSession

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness - a aplicacao esta de pe")
def health() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT,
    }


@router.get("/health/db", summary="Readiness - o banco responde")
def health_db(db: DbSession) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "up"}
