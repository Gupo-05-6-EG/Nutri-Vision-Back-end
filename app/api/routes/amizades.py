"""Endpoints do modulo social e amizades (RF05)."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, status

from app.db.deps import DbSession
from app.models.amizade import StatusAmizade
from app.schemas.amizade import (
    AmigoItem,
    AmizadeOut,
    RespostaSolicitacao,
    SolicitacaoAmizadeCreate,
)
from app.services import amizades as servico

router = APIRouter(prefix="/amizades", tags=["amizades"])

PacienteId = Annotated[int, Query(gt=0, description="Id do paciente")]
AmizadeId = Annotated[int, Path(gt=0, description="Id do registro de amizade")]


@router.post(
    "",
    response_model=AmizadeOut,
    status_code=status.HTTP_201_CREATED,
    summary="Envia uma solicitacao de amizade para outro paciente",
)
def solicitar_amizade(dados: SolicitacaoAmizadeCreate, db: DbSession) -> AmizadeOut:
    try:
        amizade = servico.solicitar_amizade(db, pac_id=dados.paciente_id, amigo_id=dados.amigo_id)
    except servico.AutoAmizadeNaoPermitida:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Nao e permitido enviar solicitacao de amizade para si mesmo",
        ) from None
    except servico.PacienteNaoEncontrado as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from None
    except servico.AmizadeJaExiste:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Os pacientes ja possuem vinculo de amizade ativo"
        ) from None
    except servico.SolicitacaoJaPendente:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Solicitacao de amizade ja enviada e pendente"
        ) from None

    return AmizadeOut.model_validate(amizade)


@router.put(
    "/{amizade_id}/responder",
    response_model=AmizadeOut,
    summary="Aceita ou recusa uma solicitacao de amizade recebida",
)
def responder_solicitacao(
    amizade_id: AmizadeId, dados: RespostaSolicitacao, db: DbSession
) -> AmizadeOut:
    try:
        amizade = servico.responder_solicitacao(
            db, amizade_id=amizade_id, paciente_id=dados.paciente_id, aceitar=dados.aceitar
        )
    except servico.AmizadeNaoEncontrada:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Amizade nao encontrada") from None
    except servico.OperacaoNaoPermitida as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e)) from None
    except servico.SolicitacaoJaRespondida as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from None

    return AmizadeOut.model_validate(amizade)


@router.get(
    "",
    response_model=list[AmigoItem],
    summary="Lista os amigos e solicitacoes de um paciente",
)
def listar_amizades(
    db: DbSession,
    paciente_id: PacienteId,
    status_filtro: Annotated[
        StatusAmizade | None,
        Query(alias="status", description="Filtra por status: pendente, aceito ou recusado"),
    ] = None,
) -> list[AmigoItem]:
    try:
        return servico.listar_amizades(db, paciente_id=paciente_id, status=status_filtro)
    except servico.PacienteNaoEncontrado as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from None


@router.delete(
    "/{amizade_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Desfaz uma amizade ou cancela uma solicitacao",
)
def remover_amizade(amizade_id: AmizadeId, paciente_id: PacienteId, db: DbSession) -> None:
    try:
        servico.remover_amizade(db, amizade_id=amizade_id, paciente_id=paciente_id)
    except servico.AmizadeNaoEncontrada:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Amizade nao encontrada") from None
    except servico.OperacaoNaoPermitida as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e)) from None
