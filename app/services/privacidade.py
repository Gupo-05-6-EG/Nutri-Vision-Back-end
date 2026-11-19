"""Operacoes de privacidade (LGPD): direitos do titular e montagem de ranking/desafio
publicos sem dados de saude (RF28, RF29, RNF06, RNF07).
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.alimento_personalizado import AlimentoPersonalizado
from app.models.consentimento import Consentimento
from app.models.desafio import Desafio, ParticipanteDesafio, StatusParticipante
from app.models.paciente import Paciente
from app.models.refeicao import Refeicao
from app.models.usuario import Perfil, Usuario
from app.models.vinculo import Vinculo
from app.schemas.privacidade import (
    DesafioPublicoItem,
    DesafioPublicoOut,
    RankingPublicoItem,
    RankingPublicoOut,
)
from app.services import amizades as amizades_servico
from app.services import gamificacao as gamificacao_servico


def listar_consentimentos(db: Session, usuario_id: int) -> list[Consentimento]:
    return list(
        db.scalars(
            select(Consentimento)
            .where(Consentimento.usuario_id == usuario_id)
            .order_by(Consentimento.aceito_em, Consentimento.id)
        )
    )


def registrar_consentimento(db: Session, usuario_id: int, versao_termo: str) -> Consentimento:
    consentimento = db.scalar(
        select(Consentimento)
        .where(
            Consentimento.usuario_id == usuario_id,
            Consentimento.revogado_em.is_(None),
            Consentimento.versao_termo == versao_termo,
        )
        .order_by(Consentimento.id.desc())
    )
    if consentimento is not None:
        return consentimento

    agora = datetime.now(UTC)
    anteriores_ativos = db.scalars(
        select(Consentimento).where(
            Consentimento.usuario_id == usuario_id,
            Consentimento.revogado_em.is_(None),
        )
    )
    for anterior in anteriores_ativos:
        anterior.revogado_em = agora

    consentimento = Consentimento(usuario_id=usuario_id, versao_termo=versao_termo)
    db.add(consentimento)
    db.commit()
    db.refresh(consentimento)
    return consentimento


def revogar_consentimento(db: Session, usuario_id: int) -> Consentimento | None:
    ativos = list(
        db.scalars(
            select(Consentimento)
            .where(Consentimento.usuario_id == usuario_id, Consentimento.revogado_em.is_(None))
            .order_by(Consentimento.id.desc())
        )
    )
    if not ativos:
        return None
    agora = datetime.now(UTC)
    for item in ativos:
        item.revogado_em = agora
    db.commit()
    consentimento = ativos[0]
    db.refresh(consentimento)
    return consentimento


def exportar_dados(db: Session, usuario: Usuario) -> dict[str, object]:
    consentimentos = listar_consentimentos(db, usuario.id)
    dados: dict[str, object] = {
        "usuario": {
            "id": usuario.id,
            "nome": usuario.nome,
            "email": usuario.email,
            "perfil": usuario.perfil,
            "criado_em": usuario.criado_em,
        },
        "consentimentos": consentimentos,
    }
    if usuario.perfil == Perfil.PACIENTE:
        paciente = db.get(Paciente, usuario.id)
        dados["paciente"] = paciente
        refeicoes = db.scalars(
            select(Refeicao)
            .where(Refeicao.paciente_id == usuario.id)
            .options(selectinload(Refeicao.itens))
            .order_by(Refeicao.consumida_em, Refeicao.id)
        ).all()
        dados["refeicoes"] = refeicoes
        dados["alimentos_personalizados"] = db.scalars(
            select(AlimentoPersonalizado)
            .where(AlimentoPersonalizado.paciente_id == usuario.id)
            .order_by(AlimentoPersonalizado.id)
        ).all()
        dados["vinculos"] = db.scalars(
            select(Vinculo).where(Vinculo.paciente_id == usuario.id).order_by(Vinculo.id)
        ).all()
    else:
        dados["vinculos"] = db.scalars(
            select(Vinculo).where(Vinculo.nutricionista_id == usuario.id).order_by(Vinculo.id)
        ).all()
    return dados


def excluir_conta(db: Session, usuario: Usuario) -> None:
    if usuario.perfil == Perfil.PACIENTE:
        db.query(AlimentoPersonalizado).filter(
            AlimentoPersonalizado.paciente_id == usuario.id
        ).delete(synchronize_session=False)
    db.delete(usuario)
    db.commit()


def obter_ranking_publico(
    db: Session,
    paciente_id: int,
    limite: int = 10,
    incluir_solicitante: bool = True,
) -> RankingPublicoOut:
    """Gera o ranking publico entre amigos expondo APENAS nome, avatar, pontos e streak (RF29).

    Garante que dados sensiveis (peso_kg, altura_cm, idade, meta_kcal, refeicoes, etc.)
    jamais sejam incluidos no retorno a terceiros.
    """
    gamificacao_servico._garantir_paciente(db, paciente_id)

    amigo_ids = amizades_servico.obter_ids_amigos_aceitos(db, paciente_id)
    participantes_ids = list(set([paciente_id] + amigo_ids)) if incluir_solicitante else amigo_ids

    inicio, fim = gamificacao_servico.janela_semanal()

    if not participantes_ids:
        return RankingPublicoOut(
            total_participantes=0,
            ranking=[],
        )

    totais_xp = gamificacao_servico.calcular_xp_semanal(db, participantes_ids, inicio, fim)

    pacientes_consulta = select(Paciente).where(Paciente.id.in_(participantes_ids))
    pacientes = {p.id: p for p in db.scalars(pacientes_consulta).all()}

    # Agrupa candidatos em DTOs publicos estritos
    candidatos = []
    for pid in participantes_ids:
        paciente = pacientes.get(pid)
        nome = _nome_publico(paciente)
        avatar = paciente.avatar if paciente else None
        pontos = totais_xp.get(pid, 0)
        streak = paciente.streak if paciente else 0

        candidatos.append(
            {
                "pid": pid,
                "item": RankingPublicoItem(
                    nome=nome,
                    avatar=avatar,
                    pontos=pontos,
                    streak=streak,
                ),
            }
        )

    # Ordenacao padrao de gamificacao: Maior pontuacao -> Maior streak -> Menor PID
    candidatos.sort(key=lambda c: (-c["item"].pontos, -c["item"].streak, c["pid"]))

    ranking_itens = [c["item"] for c in candidatos[:limite]]

    return RankingPublicoOut(
        total_participantes=len(candidatos),
        ranking=ranking_itens,
    )


class DesafioNaoEncontrado(Exception):
    """Desafio inexistente ou o solicitante nao participa dele."""


def obter_desafio_publico(db: Session, desafio_id: int, solicitante_id: int) -> DesafioPublicoOut:
    """Placar do desafio expondo APENAS nome, avatar, pontos e streak (RF05.2, RF29).

    O titulo e os participantes (convites aceitos) vem do desafio cadastrado. So
    quem participa (ou criou) enxerga o placar; para os demais o desafio "nao existe".
    """
    desafio = db.get(Desafio, desafio_id)
    if desafio is None:
        raise DesafioNaoEncontrado
    ids = list(
        db.scalars(
            select(ParticipanteDesafio.paciente_id)
            .where(
                ParticipanteDesafio.desafio_id == desafio_id,
                ParticipanteDesafio.status == StatusParticipante.ACEITO.value,
            )
            .order_by(ParticipanteDesafio.paciente_id)
        )
    )
    if solicitante_id not in ids and solicitante_id != desafio.criador_id:
        raise DesafioNaoEncontrado

    pacientes = {p.id: p for p in db.scalars(select(Paciente).where(Paciente.id.in_(ids)))}
    inicio, fim = gamificacao_servico.janela_semanal()
    totais_xp = gamificacao_servico.calcular_xp_semanal(db, ids, inicio, fim)

    participantes = []
    for pid in ids:
        paciente = pacientes.get(pid)
        participantes.append(
            DesafioPublicoItem(
                nome=_nome_publico(paciente),
                avatar=paciente.avatar if paciente else None,
                pontos=totais_xp.get(pid, 0),
                streak=paciente.streak if paciente else 0,
            )
        )
    participantes.sort(key=lambda p: (-p.pontos, -p.streak))

    return DesafioPublicoOut(
        desafio_id=desafio_id,
        titulo=desafio.nome,
        total_participantes=len(participantes),
        participantes=participantes,
    )


def _nome_publico(paciente: Paciente | None) -> str | None:
    if paciente is None:
        return None
    return paciente.nome or paciente.username
