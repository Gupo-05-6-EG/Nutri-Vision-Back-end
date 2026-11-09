"""Endpoints dos lembretes de refeicao e do token de push (Task 2.8, RF26).

Como a triagem, usam `paciente_id` no caminho por enquanto: a Task 1.6 (RNF06)
passa a exigir o token e a validar quem chama.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Response, status

from app.db.deps import DbSession
from app.schemas.lembrete_refeicao import (
    DispositivoPushIn,
    LembretesIn,
    LembretesOut,
)
from app.services import lembretes_refeicao as servico

router = APIRouter(prefix="/pacientes", tags=["lembretes-refeicao"])

PacienteId = Annotated[int, Path(gt=0, description="Id do paciente")]

NAO_ENCONTRADO = HTTPException(status.HTTP_404_NOT_FOUND, "Paciente nao encontrado")


@router.get(
    "/{paciente_id}/lembretes-refeicao",
    response_model=LembretesOut,
    summary="Lista os horarios de lembrete de refeicao do paciente",
)
def listar_lembretes(paciente_id: PacienteId, db: DbSession) -> LembretesOut:
    try:
        lembretes = servico.listar_lembretes(db, paciente_id)
    except servico.PacienteNaoEncontrado:
        raise NAO_ENCONTRADO from None
    return LembretesOut(paciente_id=paciente_id, lembretes=lembretes)


@router.put(
    "/{paciente_id}/lembretes-refeicao",
    response_model=LembretesOut,
    summary="Salva os horarios de lembrete por refeicao",
)
def salvar_lembretes(paciente_id: PacienteId, dados: LembretesIn, db: DbSession) -> LembretesOut:
    try:
        lembretes = servico.salvar_lembretes(db, paciente_id, dados)
    except servico.PacienteNaoEncontrado:
        raise NAO_ENCONTRADO from None
    return LembretesOut(paciente_id=paciente_id, lembretes=lembretes)


@router.put(
    "/{paciente_id}/dispositivos-push",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Registra o token FCM do aparelho para receber os lembretes",
)
def registrar_dispositivo(
    paciente_id: PacienteId, dados: DispositivoPushIn, db: DbSession
) -> Response:
    try:
        servico.registrar_dispositivo(db, paciente_id, dados.token)
    except servico.PacienteNaoEncontrado:
        raise NAO_ENCONTRADO from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
