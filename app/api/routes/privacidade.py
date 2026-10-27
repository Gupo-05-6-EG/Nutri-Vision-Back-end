"""Endpoints de Privacidade e Conformidade LGPD (Item 51 - RF29, RNF06, RNF07).

Rotas publicas para exibicao de rankings e desafios onde dados de saude
sao estritamente omitidos e isolados, retornando unicamente:
- nome
- avatar
- pontos
- streak
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, status

from app.db.deps import DbSession
from app.schemas.privacidade import DesafioPublicoOut, RankingPublicoOut
from app.services import gamificacao as gamificacao_servico
from app.services import privacidade as servico

router = APIRouter(prefix="/privacidade", tags=["privacidade"])

PacienteId = Annotated[int, Query(gt=0, description="Id do paciente solicitante")]
DesafioId = Annotated[int, Path(gt=0, description="Id do desafio")]
Limite = Annotated[int, Query(ge=1, le=100, description="Numero maximo de posicoes a retornar")]


@router.get(
    "/ranking-publico",
    response_model=RankingPublicoOut,
    summary="Retorna ranking publico entre amigos expondo apenas nome, avatar, pontos e streak",
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
    """Retorna o ranking publico semanal.

    Conforme LGPD (RF-29), dados de saude como peso, calorias, altura,
    metas nutricionais e refeicoes detalhadas NUNCA sao expostos a terceiros.
    """
    try:
        return servico.obter_ranking_publico(
            db,
            paciente_id=paciente_id,
            limite=limite,
            incluir_solicitante=incluir_solicitante,
        )
    except gamificacao_servico.PacienteNaoEncontrado as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from None


@router.get(
    "/desafios/{desafio_id}/publico",
    response_model=DesafioPublicoOut,
    summary="Retorna detalhes e participantes de um desafio publico com dados restritos",
)
def obter_desafio_publico(
    db: DbSession,
    desafio_id: DesafioId,
    titulo: Annotated[str, Query(description="Titulo do desafio")] = "Desafio Semanal",
    participantes: Annotated[
        str | None,
        Query(description="Lista de IDs de pacientes separados por virgula (ex: 1,2,3)"),
    ] = None,
) -> DesafioPublicoOut:
    """Retorna o placar publico do desafio.

    Restringe os dados dos participantes estritamente a: nome, avatar, pontos e streak.
    Nenhum dado clinico individual e exposto aos demais concorrentes.
    """
    pids = []
    if participantes:
        try:
            pids = [int(p.strip()) for p in participantes.split(",") if p.strip()]
        except ValueError:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Parametro 'participantes' deve conter inteiros separados por virgula",
            ) from None

    return servico.obter_desafio_publico(
        db,
        desafio_id=desafio_id,
        titulo=titulo,
        participante_ids=pids,
    )
