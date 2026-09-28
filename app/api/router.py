"""Agregador das rotas da API v1."""

from fastapi import APIRouter

from app.api.routes import alimentos_taco, auth, health, pacientes, refeicoes

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(alimentos_taco.router)
api_router.include_router(pacientes.router)
api_router.include_router(refeicoes.router)
