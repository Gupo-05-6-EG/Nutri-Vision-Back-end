"""Endpoints de privacidade (LGPD): consentimento e direitos do titular (RF28, RNF07) e
rankings/desafios publicos que expoem apenas nome, avatar, pontos e streak (RF29, RNF06).
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Response, status

from app.api.deps import UsuarioAtual
from app.db.deps import DbSession
from app.models.consentimento import Consentimento
from app.schemas.privacidade import (
    ConsentimentoIn,
    ConsentimentoOut,
    ConsentimentoStatusOut,
    DesafioPublicoOut,
    RankingPublicoOut,
)
from app.services import gamificacao as gamificacao_servico
from app.services import privacidade as servico

router = APIRouter(prefix="/privacidade", tags=["privacidade"])


def _consentimento_out(item: Consentimento) -> ConsentimentoOut:
    return ConsentimentoOut(
        versao_termo=item.versao_termo,
        aceito_em=item.aceito_em,
        revogado_em=item.revogado_em,
    )


@router.get("/consentimento", response_model=ConsentimentoStatusOut)
def obter_consentimento(usuario: UsuarioAtual, db: DbSession) -> ConsentimentoStatusOut:
    itens = servico.listar_consentimentos(db, usuario.id)
    return ConsentimentoStatusOut(
        consentimentos=[_consentimento_out(item) for item in itens],
        consentimento_ativo=bool(itens and itens[-1].revogado_em is None),
    )


@router.post(
    "/consentimento",
    response_model=ConsentimentoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Registra o aceite de uma versao do termo",
)
def aceitar_consentimento(
    dados: ConsentimentoIn, usuario: UsuarioAtual, db: DbSession
) -> ConsentimentoOut:
    item = servico.registrar_consentimento(db, usuario.id, dados.versao_termo.strip())
    return _consentimento_out(item)


@router.post("/consentimento/revogar", response_model=ConsentimentoOut)
def revogar_consentimento(usuario: UsuarioAtual, db: DbSession) -> ConsentimentoOut:
    item = servico.revogar_consentimento(db, usuario.id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nenhum consentimento ativo")
    return _consentimento_out(item)


@router.get("/dados", summary="Exporta os dados pessoais do titular")
def exportar_dados(usuario: UsuarioAtual, db: DbSession) -> dict[str, object]:
    return servico.exportar_dados(db, usuario)


@router.delete("/conta", status_code=status.HTTP_204_NO_CONTENT)
def excluir_conta(usuario: UsuarioAtual, db: DbSession) -> Response:
    servico.excluir_conta(db, usuario)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
