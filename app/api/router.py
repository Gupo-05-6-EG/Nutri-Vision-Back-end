"""Agregador das rotas da API v1."""

from fastapi import APIRouter

from app.api.routes import alimentos_taco, health, pacientes, refeicoes, vinculos

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(alimentos_taco.router)
api_router.include_router(pacientes.router)
api_router.include_router(refeicoes.router)
api_router.include_router(vinculos.router)
