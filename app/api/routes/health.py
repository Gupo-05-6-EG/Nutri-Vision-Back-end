"""Endpoints de healthcheck (RNF09 - monitoramento).

- `/health` (liveness): o processo responde. Use no HEALTHCHECK do container.
- `/health/db` (readiness): o banco tambem responde; `503` se nao. Use no
  monitor de uptime e no balanceador, para tirar a instancia de rotacao.
"""

import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.db.deps import DbSession

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health", summary="Liveness - a aplicacao esta de pe")
def health() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT,
    }


@router.get(
    "/health/db",
    summary="Readiness - o banco responde",
    responses={503: {"description": "Banco indisponivel"}},
)
def health_db(db: DbSession) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("readiness: banco indisponivel")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Banco indisponivel") from None
    return {"status": "ok", "database": "up"}
