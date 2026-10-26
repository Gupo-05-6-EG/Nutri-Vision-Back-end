"""Endpoints de registro e historico de refeicoes (RF04, RF12).

`paciente_id` ainda chega por parametro: a Task 1.6 (RNF06) passa a exigir o
token (`app.api.deps.UsuarioAtual`) e a validar se quem chama e o proprio
paciente ou um nutricionista vinculado.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.db.deps import DbSession
from app.models.refeicao import TipoRefeicao
from app.schemas.refeicao import ConsumoDiario, RefeicaoCreate, RefeicaoOut, RefeicaoUpdate
from app.services import refeicoes as servico

router = APIRouter(prefix="/refeicoes", tags=["refeicoes"])

PacienteId = Annotated[int, Query(gt=0, description="Id do paciente")]
Dia = Annotated[date, Query(description="Dia do consumo (YYYY-MM-DD, em UTC)")]
DiaOpcional = Annotated[date | None, Query(description="Filtra por um dia (YYYY-MM-DD, em UTC)")]
TipoOpcional = Annotated[
    TipoRefeicao | None,
    Query(description="Filtra por tipo: cafe_da_manha, almoco, lanche ou jantar"),
]


@router.post(
    "",
    response_model=RefeicaoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Registra uma refeicao com seus itens",
)
def registrar_refeicao(dados: RefeicaoCreate, db: DbSession) -> RefeicaoOut:
    try:
        refeicao = servico.criar_refeicao(db, dados)
    except servico.PacienteNaoEncontrado:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="paciente_id nao corresponde a um paciente cadastrado",
        ) from None
    except servico.DataDeConsumoNoFuturo:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="consumida_em nao pode estar no futuro",
        ) from None
    return RefeicaoOut.model_validate(refeicao)


@router.get("", response_model=list[RefeicaoOut], summary="Lista as refeicoes de um paciente")
def listar_refeicoes(
    db: DbSession,
    paciente_id: PacienteId,
    data: DiaOpcional = None,
    tipo: TipoOpcional = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
    deslocamento: Annotated[int, Query(ge=0)] = 0,
) -> list[RefeicaoOut]:
    refeicoes = servico.listar_refeicoes(
        db, paciente_id, dia=data, tipo=tipo, limite=limite, deslocamento=deslocamento
    )
    return [RefeicaoOut.model_validate(refeicao) for refeicao in refeicoes]


@router.get(
    "/consumo-diario",
    response_model=ConsumoDiario,
    summary="Consumo de um dia com os totais de calorias e macros",
)
def consumo_diario(
    db: DbSession, paciente_id: PacienteId, data: Dia, tipo: TipoOpcional = None
) -> ConsumoDiario:
    return ConsumoDiario.model_validate(servico.consumo_diario(db, paciente_id, data, tipo=tipo))


@router.get("/{refeicao_id}", response_model=RefeicaoOut, summary="Detalhe de uma refeicao")
def detalhar_refeicao(refeicao_id: int, db: DbSession) -> RefeicaoOut:
    try:
        refeicao = servico.buscar_refeicao(db, refeicao_id)
    except servico.RefeicaoNaoEncontrada:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Refeicao nao encontrada") from None
    return RefeicaoOut.model_validate(refeicao)


@router.put("/{refeicao_id}", response_model=RefeicaoOut, summary="Atualiza uma refeicao")
def atualizar_refeicao(refeicao_id: int, dados: RefeicaoUpdate, db: DbSession) -> RefeicaoOut:
    try:
        refeicao = servico.atualizar_refeicao(db, refeicao_id, dados)
    except servico.RefeicaoNaoEncontrada:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Refeicao nao encontrada") from None
    except servico.DataDeConsumoNoFuturo:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="consumida_em nao pode estar no futuro",
        ) from None
    return RefeicaoOut.model_validate(refeicao)


@router.delete(
    "/{refeicao_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove uma refeicao e seus itens",
)
def remover_refeicao(refeicao_id: int, db: DbSession) -> None:
    try:
        servico.remover_refeicao(db, refeicao_id)
    except servico.RefeicaoNaoEncontrada:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Refeicao nao encontrada") from None
