"""Endpoints de alimentos personalizados e busca unificada (RF22).

Consumido pela Task 2.6 [Front]. `paciente_id` chega por parametro/corpo
enquanto nao existe autenticacao; a Task 1.2 passa a tirar o paciente do token
JWT e a Task 1.6 aplica o controle de acesso.

A busca por `/alimentos-taco` continua existindo, so com a TACO.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.db.deps import DbSession
from app.schemas.alimento_personalizado import (
    AlimentoBuscaOut,
    AlimentoPersonalizadoCreate,
    AlimentoPersonalizadoOut,
)
from app.services import alimento_personalizado as servico

router = APIRouter(tags=["alimentos-personalizados"])

Nome = Annotated[str, Query(min_length=1, description="Trecho do nome do alimento")]
PacienteOpcional = Annotated[
    int | None,
    Query(gt=0, description="Inclui os alimentos personalizados deste paciente na busca"),
]


@router.post(
    "/alimentos-personalizados",
    response_model=AlimentoPersonalizadoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra um alimento sem correspondencia na TACO (valores por 100g)",
)
def cadastrar_alimento(
    dados: AlimentoPersonalizadoCreate, db: DbSession
) -> AlimentoPersonalizadoOut:
    try:
        alimento = servico.criar_alimento(db, dados)
    except servico.AlimentoJaCadastrado:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Ja existe um alimento personalizado com esse nome"
        ) from None
    return AlimentoPersonalizadoOut.model_validate(alimento)


@router.get(
    "/alimentos",
    response_model=list[AlimentoBuscaOut],
    summary="Busca unificada por nome: TACO + alimentos personalizados do paciente",
)
def buscar_alimentos(
    db: DbSession,
    nome: Nome,
    paciente_id: PacienteOpcional = None,
    limite: Annotated[int, Query(ge=1, le=100)] = 20,
    deslocamento: Annotated[int, Query(ge=0)] = 0,
) -> list[AlimentoBuscaOut]:
    return servico.buscar_alimentos(
        db, nome, paciente_id=paciente_id, limite=limite, deslocamento=deslocamento
    )
