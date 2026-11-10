"""Endpoints de desafios e placares entre pacientes (RF05.2, RF05.3)."""

from fastapi import APIRouter, HTTPException, status

from app.api.deps import UsuarioAtual
from app.db.deps import DbSession
from app.models.desafio import StatusParticipante
from app.schemas.desafio import (
    ConvidarIn,
    DesafioCriarIn,
    DesafioOut,
    ParticipanteOut,
    PlacarItemOut,
    PlacarOut,
    ResponderConviteIn,
)
from app.services import desafios as servico

router = APIRouter(prefix="/challenges", tags=["desafios"])


def _http_error(erro: Exception) -> None:
    if isinstance(erro, servico.DesafioNaoEncontrado):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Desafio ou convite nao encontrado"
        ) from None
    if isinstance(erro, servico.SemPermissaoDesafio):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Acesso nao autorizado ao desafio") from None
    if isinstance(erro, servico.ConviteInvalido):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Convite ou dados de participantes invalidos"
        ) from None


@router.post("", response_model=DesafioOut, status_code=status.HTTP_201_CREATED)
def criar_desafio(dados: DesafioCriarIn, db: DbSession, usuario: UsuarioAtual) -> DesafioOut:
    try:
        desafio = servico.criar_desafio(db, usuario, dados)
    except (servico.SemPermissaoDesafio, servico.ConviteInvalido) as erro:
        _http_error(erro)
    return DesafioOut.model_validate(desafio).model_copy(
        update={"status": StatusParticipante.ACEITO}
    )


@router.post("/{desafio_id}/invites", response_model=list[ParticipanteOut], status_code=201)
def convidar(
    desafio_id: int, dados: ConvidarIn, db: DbSession, usuario: UsuarioAtual
) -> list[ParticipanteOut]:
    try:
        participantes = servico.convidar(db, usuario, desafio_id, dados.pacientes)
    except (
        servico.DesafioNaoEncontrado,
        servico.SemPermissaoDesafio,
        servico.ConviteInvalido,
    ) as erro:
        _http_error(erro)
    return [
        ParticipanteOut(paciente_id=paciente_id, nome=nome, status="convidado")
        for paciente_id, nome in participantes
    ]


@router.post("/{desafio_id}/response", response_model=ParticipanteOut)
def responder_convite(
    desafio_id: int, dados: ResponderConviteIn, db: DbSession, usuario: UsuarioAtual
) -> ParticipanteOut:
    try:
        participante = servico.responder_convite(db, usuario, desafio_id, dados.aceitar)
    except (
        servico.DesafioNaoEncontrado,
        servico.SemPermissaoDesafio,
        servico.ConviteInvalido,
    ) as erro:
        _http_error(erro)
    return ParticipanteOut(paciente_id=usuario.id, nome=usuario.nome, status=participante.status)


@router.get("", response_model=list[DesafioOut])
def listar_desafios(db: DbSession, usuario: UsuarioAtual) -> list[DesafioOut]:
    try:
        desafios = servico.listar_desafios(db, usuario)
    except servico.SemPermissaoDesafio as erro:
        _http_error(erro)
    return [
        DesafioOut.model_validate(desafio).model_copy(
            update={"status": StatusParticipante(status_)}
        )
        for desafio, status_ in desafios
    ]


@router.get("/{desafio_id}/leaderboard", response_model=PlacarOut)
def obter_placar(desafio_id: int, db: DbSession, usuario: UsuarioAtual) -> PlacarOut:
    try:
        tipo, linhas = servico.obter_placar(db, usuario, desafio_id)
    except (servico.DesafioNaoEncontrado, servico.SemPermissaoDesafio) as erro:
        _http_error(erro)
    unidade = {
        "refeicoes": "refeicoes",
        "variacao_calorica": "kcal/dia (menor vence)",
        "sequencia_meta": "dias consecutivos",
    }[tipo]
    return PlacarOut(
        desafio_id=desafio_id,
        tipo=tipo,
        participantes=[
            PlacarItemOut(
                posicao=posicao,
                paciente_id=paciente_id,
                nome=nome,
                pontuacao=pontuacao,
                unidade=unidade,
            )
            for posicao, (paciente_id, nome, pontuacao) in enumerate(linhas, start=1)
        ],
    )
