"""Endpoints de Gamificacao e Leaderboard Semanal (RF05, RF16, RF29)."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, status

from app.db.deps import DbSession
from app.schemas.gamificacao import (
    DesafioPublicoOut,
    HistoricoXPOut,
    LeaderboardOut,
    RankingPublicoOut,
    RegistroXPIn,
)
from app.services import gamificacao as servico

router = APIRouter(prefix="/gamificacao", tags=["gamificacao"])

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


@router.get(
    "/ranking-publico",
    response_model=RankingPublicoOut,
    summary="Ranking publico entre amigos expondo apenas nome, avatar, pontos e streak",
)
def obter_ranking_publico(
    db: DbSession,
    paciente_id: PacienteId,
    limite: Limite = 10,
    incluir_solicitante: Annotated[
        bool,
        Query(description="Inclui o proprio solicitante no placar para comparacao"),
    ] = True,
) -> RankingPublicoOut:
    from app.services import privacidade as privacidade_servico

    try:
        return privacidade_servico.obter_ranking_publico(
            db,
            paciente_id=paciente_id,
            limite=limite,
            incluir_solicitante=incluir_solicitante,
        )
    except servico.PacienteNaoEncontrado as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from None


@router.get(
    "/desafios/{desafio_id}/publico",
    response_model=DesafioPublicoOut,
    summary="Detalhes e participantes de desafio publico sem expor dados clinicos",
)
def obter_desafio_publico(
    db: DbSession,
    desafio_id: Annotated[int, Path(gt=0, description="Id do desafio")],
    titulo: Annotated[str, Query(description="Titulo do desafio")] = "Desafio Semanal",
    participantes: Annotated[
        str | None,
        Query(description="Lista de IDs de pacientes separados por virgula (ex: 1,2,3)"),
    ] = None,
) -> DesafioPublicoOut:
    from app.services import privacidade as privacidade_servico

    pids = []
    if participantes:
        try:
            pids = [int(p.strip()) for p in participantes.split(",") if p.strip()]
        except ValueError:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Parametro 'participantes' deve conter inteiros separados por virgula",
            ) from None

    return privacidade_servico.obter_desafio_publico(
        db,
        desafio_id=desafio_id,
        titulo=titulo,
        participante_ids=pids,
    )


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
