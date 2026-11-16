"""Endpoints de Gamificacao: ofensiva e resgate de bloqueio (RF17) e Leaderboard Semanal
(RF05, RF16, RF29)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict

from app.api.deps import exigir_perfil
from app.db.deps import DbSession
from app.models.paciente import Paciente
from app.models.usuario import Perfil, Usuario
from app.schemas.gamificacao import (
    HistoricoXPOut,
    LeaderboardOut,
    RegistroXPIn,
)
from app.services import gamificacao as servico

router = APIRouter(prefix="/gamificacao", tags=["gamificacao"])
PacienteAtual = Annotated[Usuario, Depends(exigir_perfil(Perfil.PACIENTE))]

PacienteId = Annotated[int, Query(gt=0, description="Id do paciente solicitante")]
Limite = Annotated[int, Query(ge=1, le=100, description="Numero maximo de posicoes a retornar")]
Deslocamento = Annotated[int, Query(ge=0, description="Deslocamento para paginacao")]


@router.get(
    "/leaderboard",
    response_model=LeaderboardOut,
    summary="Retorna os Top 10 amigos ordenados pelo ganho de XP na janela semanal",
)
def obter_leaderboard(
    db: DbSession,
    paciente_id: PacienteId,
    limite: Limite = 10,
    incluir_solicitante: Annotated[
        bool,
        Query(description="Inclui o proprio solicitante no placar para comparar seu desempenho"),
    ] = True,
) -> LeaderboardOut:
    try:
        return servico.obter_leaderboard_semanal(
            db,
            paciente_id=paciente_id,
            limite=limite,
            incluir_solicitante=incluir_solicitante,
        )
    except servico.PacienteNaoEncontrado as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from None


@router.post(
    "/xp",
    response_model=HistoricoXPOut,
    status_code=status.HTTP_201_CREATED,
    summary="Concede pontos de experiencia (XP) ao paciente",
)
def conceder_xp(dados: RegistroXPIn, db: DbSession) -> HistoricoXPOut:
    try:
        registro = servico.conceder_xp(
            db,
            paciente_id=dados.paciente_id,
            quantidade=dados.quantidade,
            motivo=dados.motivo,
        )
    except servico.PacienteNaoEncontrado as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from None

    return HistoricoXPOut.model_validate(registro)


@router.get(
    "/historico-xp",
    response_model=list[HistoricoXPOut],
    summary="Lista o historico de ganhos de XP de um paciente",
)
def listar_historico_xp(
    db: DbSession,
    paciente_id: PacienteId,
    limite: Limite = 50,
    deslocamento: Deslocamento = 0,
) -> list[HistoricoXPOut]:
    try:
        registros = servico.listar_historico_xp(
            db, paciente_id=paciente_id, limite=limite, deslocamento=deslocamento
        )
    except servico.PacienteNaoEncontrado as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from None

    return [HistoricoXPOut.model_validate(r) for r in registros]


class OfensivaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    streak: int
    xp: int
    bloqueios_perda: int
    custo_bloqueio_xp: int = servico.CUSTO_BLOQUEIO_XP


@router.get("")
def consultar_ofensiva(db: DbSession, usuario: PacienteAtual) -> OfensivaOut:
    paciente = db.get(Paciente, usuario.id)
    if paciente is None:
        raise HTTPException(404, "Paciente nao encontrado")
    return OfensivaOut.model_validate(paciente)


@router.post("/bloqueios")
def comprar_bloqueio(db: DbSession, usuario: PacienteAtual) -> OfensivaOut:
    paciente = servico.resgatar_bloqueio(db, usuario.id)
    if paciente is None:
        raise HTTPException(409, "XP insuficiente para resgatar o bloqueio")
    return OfensivaOut.model_validate(paciente)
