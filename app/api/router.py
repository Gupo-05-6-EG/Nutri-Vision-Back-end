"""Agregador das rotas da API v1."""

from fastapi import APIRouter

from app.api.routes import health, refeicoes

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(refeicoes.router)
