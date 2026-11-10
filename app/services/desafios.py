"""Regras de negócio para convites e placares dos desafios sociais."""

from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.desafio import (
    Desafio,
    ParticipanteDesafio,
    StatusParticipante,
    TipoDesafio,
)
from app.models.paciente import Paciente
from app.models.refeicao import ItemRefeicao, Refeicao, TipoRefeicao
from app.models.usuario import Perfil, Usuario

FUSO_HORARIO = ZoneInfo("America/Sao_Paulo")
PERCENTUAL_TOLERANCIA_META = Decimal("0.30")


class DesafioNaoEncontrado(Exception):
    pass


class SemPermissaoDesafio(Exception):
    pass


class ConviteInvalido(Exception):
    pass


def _garantir_pacientes(db: Session, ids: list[int]) -> None:
    if len(set(ids)) != len(ids):
        raise ConviteInvalido
    if ids and len(db.scalars(select(Paciente.id).where(Paciente.id.in_(ids))).all()) != len(ids):
        raise ConviteInvalido


def criar_desafio(db: Session, usuario: Usuario, dados) -> Desafio:
    if usuario.perfil != Perfil.PACIENTE.value:
        raise SemPermissaoDesafio
    if dados.inicio_em.tzinfo is None or dados.fim_em.tzinfo is None:
        raise ConviteInvalido
    if dados.fim_em <= dados.inicio_em:
        raise ConviteInvalido
    ids = [paciente_id for paciente_id in dados.convidados if paciente_id != usuario.id]
    if len(ids) != len(dados.convidados):
        raise ConviteInvalido
    _garantir_pacientes(db, ids)

    desafio = Desafio(
        criador_id=usuario.id,
        nome=dados.nome,
        tipo=dados.tipo.value,
        regra=dados.regra,
        inicio_em=dados.inicio_em.astimezone(UTC),
        fim_em=dados.fim_em.astimezone(UTC),
    )
    db.add(desafio)
    db.flush()
    db.add(
        ParticipanteDesafio(
            desafio_id=desafio.id, paciente_id=usuario.id, status=StatusParticipante.ACEITO.value
        )
    )
    db.add_all(
        ParticipanteDesafio(
            desafio_id=desafio.id,
            paciente_id=paciente_id,
            status=StatusParticipante.CONVIDADO.value,
        )
        for paciente_id in ids
    )
    db.commit()
    db.refresh(desafio)
    return desafio


def convidar(
    db: Session, usuario: Usuario, desafio_id: int, ids: list[int]
) -> list[tuple[int, str]]:
    desafio = db.get(Desafio, desafio_id)
    if desafio is None:
        raise DesafioNaoEncontrado
    if desafio.criador_id != usuario.id:
        raise SemPermissaoDesafio
    if usuario.perfil != Perfil.PACIENTE.value:
        raise SemPermissaoDesafio
    if usuario.id in ids:
        raise ConviteInvalido
    _garantir_pacientes(db, ids)
    existentes = set(
        db.scalars(
            select(ParticipanteDesafio.paciente_id).where(
                ParticipanteDesafio.desafio_id == desafio_id,
                ParticipanteDesafio.paciente_id.in_(ids),
            )
        ).all()
    ) if ids else set()
    if existentes:
        raise ConviteInvalido
    db.add_all(
        ParticipanteDesafio(
            desafio_id=desafio_id,
            paciente_id=paciente_id,
            status=StatusParticipante.CONVIDADO.value,
        )
        for paciente_id in ids
    )
    db.commit()
    nomes = db.execute(
        select(Paciente.id, Usuario.nome)
        .join(Usuario, Usuario.id == Paciente.id)
        .where(Paciente.id.in_(ids))
    ).all()
    return list(nomes)


def responder_convite(
    db: Session, usuario: Usuario, desafio_id: int, aceitar: bool
) -> ParticipanteDesafio:
    if usuario.perfil != Perfil.PACIENTE.value:
        raise SemPermissaoDesafio
    participante = db.scalar(
        select(ParticipanteDesafio).where(
            ParticipanteDesafio.desafio_id == desafio_id,
            ParticipanteDesafio.paciente_id == usuario.id,
        )
    )
    if participante is None:
        raise DesafioNaoEncontrado
    if participante.status != StatusParticipante.CONVIDADO.value:
        raise ConviteInvalido
    participante.status = (
        StatusParticipante.ACEITO.value if aceitar else StatusParticipante.RECUSADO.value
    )
    participante.respondido_em = datetime.now(UTC)
    db.commit()
    db.refresh(participante)
    return participante


def listar_desafios(db: Session, usuario: Usuario) -> list[tuple[Desafio, str]]:
    if usuario.perfil != Perfil.PACIENTE.value:
        raise SemPermissaoDesafio
    rows = db.execute(
        select(Desafio, ParticipanteDesafio.status)
        .join(ParticipanteDesafio, ParticipanteDesafio.desafio_id == Desafio.id)
        .where(ParticipanteDesafio.paciente_id == usuario.id)
        .order_by(Desafio.inicio_em.desc())
    )
    return list(rows.all())


def _pontuacoes(
    db: Session, desafio: Desafio, tipo: str
) -> list[tuple[int, str, Decimal | None]]:
    membros = db.execute(
        select(ParticipanteDesafio.paciente_id, Usuario.nome)
        .join(Usuario, Usuario.id == ParticipanteDesafio.paciente_id)
        .where(
            ParticipanteDesafio.desafio_id == desafio.id,
            ParticipanteDesafio.status == StatusParticipante.ACEITO.value,
        )
    ).all()
    paciente_ids = [paciente_id for paciente_id, _ in membros]
    if not paciente_ids:
        return []
    refeicoes = db.execute(
        select(
            Refeicao.id,
            Refeicao.paciente_id,
            Refeicao.consumida_em,
            Refeicao.tipo,
            ItemRefeicao.calorias_kcal,
        )
        .outerjoin(ItemRefeicao, ItemRefeicao.refeicao_id == Refeicao.id)
        .where(
            Refeicao.paciente_id.in_(paciente_ids),
            Refeicao.consumida_em >= desafio.inicio_em,
            Refeicao.consumida_em <= desafio.fim_em,
        )
    ).all()
    por_dia: dict[int, dict[date, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    refeicoes_por_dia: dict[int, dict[date, set[int]]] = defaultdict(lambda: defaultdict(set))
    tipos_por_dia: dict[int, dict[date, set[str]]] = defaultdict(lambda: defaultdict(set))
    for refeicao_id, paciente_id, consumida_em, tipo_refeicao, calorias in refeicoes:
        local = (
            consumida_em.replace(tzinfo=UTC).astimezone(FUSO_HORARIO)
            if consumida_em.tzinfo is None
            else consumida_em.astimezone(FUSO_HORARIO)
        )
        por_dia[paciente_id][local.date()] += Decimal(calorias or 0)
        refeicoes_por_dia[paciente_id][local.date()].add(refeicao_id)
        tipos_por_dia[paciente_id][local.date()].add(tipo_refeicao)

    metas = dict(
        db.execute(
            select(Paciente.id, Paciente.meta_kcal).where(Paciente.id.in_(paciente_ids))
        ).all()
    )
    resultado = []
    inicio_em = desafio.inicio_em
    fim_em = desafio.fim_em
    inicio = (
        inicio_em.replace(tzinfo=UTC) if inicio_em.tzinfo is None else inicio_em
    ).astimezone(FUSO_HORARIO).date()
    fim = (fim_em.replace(tzinfo=UTC) if fim_em.tzinfo is None else fim_em).astimezone(
        FUSO_HORARIO
    ).date()
    dias = max(1, (fim - inicio).days + 1)
    for paciente_id, nome in membros:
        totais = por_dia[paciente_id]
        if tipo == TipoDesafio.REFEICOES.value:
            tipos_esperados = {tipo_refeicao.value for tipo_refeicao in TipoRefeicao}
            pontuacao = Decimal(
                sum(
                    tipos_por_dia[paciente_id][
                        inicio.fromordinal(inicio.toordinal() + offset)
                    ] >= tipos_esperados
                    for offset in range(dias)
                )
            )
        elif tipo == TipoDesafio.VARIACAO_CALORICA.value:
            meta = metas.get(paciente_id)
            pontuacao = (
                sum(
                    (
                        abs(
                            totais.get(
                                inicio.fromordinal(inicio.toordinal() + offset), Decimal(0)
                            )
                            - meta
                        )
                        for offset in range(dias)
                    ),
                    Decimal(0),
                )
                / dias
                if meta is not None
                else None
            )
        else:
            meta = metas.get(paciente_id)
            streak = melhor = 0
            for offset in range(dias):
                dia = inicio.fromordinal(inicio.toordinal() + offset)
                calorias_dia = totais.get(dia, Decimal(0))
                if (
                    meta is not None
                    and len(refeicoes_por_dia[paciente_id][dia]) >= 2
                    and calorias_dia <= meta * PERCENTUAL_TOLERANCIA_META
                ):
                    streak += 1
                    melhor = max(melhor, streak)
                else:
                    streak = 0
            pontuacao = Decimal(melhor)
        resultado.append((paciente_id, nome, pontuacao))
    return resultado


def obter_placar(
    db: Session, usuario: Usuario, desafio_id: int
) -> tuple[str, list[tuple[int, str, Decimal | None]]]:
    if usuario.perfil != Perfil.PACIENTE.value:
        raise SemPermissaoDesafio
    desafio = db.get(Desafio, desafio_id)
    if desafio is None:
        raise DesafioNaoEncontrado
    membro = db.scalar(
        select(ParticipanteDesafio.id).where(
            ParticipanteDesafio.desafio_id == desafio_id,
            ParticipanteDesafio.paciente_id == usuario.id,
            ParticipanteDesafio.status == StatusParticipante.ACEITO.value,
        )
    )
    if membro is None:
        raise SemPermissaoDesafio
    linhas = _pontuacoes(db, desafio, desafio.tipo)
    linhas.sort(
        key=lambda linha: (
            linha[2] is None,
            linha[2] or Decimal(0),
            linha[1].casefold(),
        ),
        reverse=desafio.tipo != TipoDesafio.VARIACAO_CALORICA.value,
    )
    return desafio.tipo, linhas
