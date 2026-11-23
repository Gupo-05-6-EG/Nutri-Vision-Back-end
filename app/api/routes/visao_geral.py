"""Visao geral da carteira do nutricionista (painel: Visao Geral e Pacientes & Vinculos)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.api.deps import exigir_perfil
from app.db.deps import DbSession
from app.models.usuario import Perfil, Usuario
from app.schemas.visao_geral import VisaoGeralOut
from app.services import visao_geral as servico

router = APIRouter(prefix="/nutricionista", tags=["nutricionista"])
NutricionistaAtual = Annotated[Usuario, Depends(exigir_perfil(Perfil.NUTRICIONISTA))]


@router.get(
    "/visao-geral",
    response_model=VisaoGeralOut,
    summary="Indicadores da carteira e monitoramento dos pacientes",
)
def visao_geral(
    db: DbSession,
    nutricionista: NutricionistaAtual,
    status: Annotated[
        Literal["todos", "ativos", "em_risco", "pendentes"],
        Query(description="Filtro da lista (as contagens sempre vem completas)"),
    ] = "todos",
    busca: Annotated[str | None, Query(max_length=120)] = None,
    pagina: Annotated[int, Query(ge=1)] = 1,
    por_pagina: Annotated[int, Query(ge=1, le=100)] = 10,
) -> VisaoGeralOut:
    return servico.montar_visao_geral(
        db, nutricionista.id, filtro=status, busca=busca, pagina=pagina, por_pagina=por_pagina
    )
