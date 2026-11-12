"""Agregador das rotas da API v1."""

from fastapi import APIRouter

from app.api.routes import (
    alimentos_personalizados,
    alimentos_taco,
    auth,
    calculo_nutricional,
    desafios,
    gamificacao,
    health,
    lembretes_refeicao,
    pacientes,
    planos_alimentares,
    privacidade,
    refeicoes,
    relatorios,
    vinculos,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(alimentos_taco.router)
api_router.include_router(alimentos_personalizados.router)
api_router.include_router(pacientes.router)
api_router.include_router(privacidade.router)
api_router.include_router(planos_alimentares.router)
api_router.include_router(lembretes_refeicao.router)
api_router.include_router(refeicoes.router)
api_router.include_router(calculo_nutricional.router)
api_router.include_router(vinculos.router)
api_router.include_router(desafios.router)

api_router.include_router(gamificacao.router)

api_router.include_router(relatorios.router)
