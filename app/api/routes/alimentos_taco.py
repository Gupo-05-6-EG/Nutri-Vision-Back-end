"""Endpoint de busca no Banco Nutricional TACO (RF02.2).

Consumido pela Task 2.2 [Front] para a busca e selecao de alimentos ao
montar uma refeicao.
"""

from typing import Annotated

from fastapi import APIRouter, Query

from app.db.deps import DbSession
from app.schemas.alimento_taco import AlimentoTacoOut
from app.services import alimento_taco as servico

router = APIRouter(prefix="/alimentos-taco", tags=["alimentos-taco"])

Nome = Annotated[str, Query(min_length=1, description="Trecho do nome do alimento")]


@router.get("", response_model=list[AlimentoTacoOut], summary="Busca alimentos da TACO por nome")
def buscar_alimentos(
    db: DbSession,
    nome: Nome,
    limite: Annotated[int, Query(ge=1, le=100)] = 20,
    deslocamento: Annotated[int, Query(ge=0)] = 0,
) -> list[AlimentoTacoOut]:
    alimentos = servico.buscar_por_nome(db, nome, limite=limite, deslocamento=deslocamento)
    return [AlimentoTacoOut.model_validate(alimento) for alimento in alimentos]
