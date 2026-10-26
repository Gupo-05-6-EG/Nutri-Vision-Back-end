"""Regras de negocio das refeicoes (RF04, RF12, RF19)."""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.paciente import Paciente
from app.models.refeicao import CAMPOS_NUTRICIONAIS, ItemRefeicao, Refeicao, TipoRefeicao, somar
from app.schemas.refeicao import RefeicaoCreate, RefeicaoUpdate

# Janelas de horario (hora local tratada como UTC, igual ao resto da app -
# ver `_em_utc`) usadas para sugerir o tipo quando o cliente nao informa um.
# Fora das janelas de cafe/almoco/jantar cai em lanche, que funciona como
# categoria coringa (ex.: uma refeicao registrada de madrugada).
_JANELAS_SUGESTAO: tuple[tuple[int, int, TipoRefeicao], ...] = (
    (5, 11, TipoRefeicao.CAFE_DA_MANHA),
    (11, 15, TipoRefeicao.ALMOCO),
    (18, 22, TipoRefeicao.JANTAR),
)


class RefeicaoNaoEncontrada(Exception):
    """Nao existe refeicao com o id informado."""


class PacienteNaoEncontrado(Exception):
    """`paciente_id` nao corresponde a um paciente cadastrado."""


class DataDeConsumoNoFuturo(Exception):
    """`consumida_em` esta a frente do momento atual."""


def _em_utc(momento: datetime) -> datetime:
    """Normaliza para UTC. Sem fuso, assume que o valor ja esta em UTC."""
    if momento.tzinfo is None:
        return momento.replace(tzinfo=UTC)
    return momento.astimezone(UTC)


def _validar_consumida_em(momento: datetime) -> datetime:
    normalizado = _em_utc(momento)
    # Um minuto de folga absorve relogios levemente adiantados no celular.
    if normalizado > datetime.now(UTC) + timedelta(minutes=1):
        raise DataDeConsumoNoFuturo
    return normalizado


def sugerir_tipo(consumida_em: datetime) -> TipoRefeicao:
    """Sugere o tipo da refeicao a partir da hora de `consumida_em` (RF19)."""
    hora = _em_utc(consumida_em).hour
    for inicio, fim, tipo in _JANELAS_SUGESTAO:
        if inicio <= hora < fim:
            return tipo
    return TipoRefeicao.LANCHE


def _intervalo_do_dia(dia: date) -> tuple[datetime, datetime]:
    """Limites [inicio, fim) do dia em UTC."""
    inicio = datetime.combine(dia, time.min, tzinfo=UTC)
    return inicio, inicio + timedelta(days=1)


def criar_refeicao(db: Session, dados: RefeicaoCreate) -> Refeicao:
    if db.get(Paciente, dados.paciente_id) is None:
        raise PacienteNaoEncontrado
    consumida_em = _validar_consumida_em(dados.consumida_em)
    refeicao = Refeicao(
        paciente_id=dados.paciente_id,
        consumida_em=consumida_em,
        tipo=dados.tipo or sugerir_tipo(consumida_em),
        observacao=dados.observacao,
        itens=[ItemRefeicao(**item.model_dump()) for item in dados.itens],
    )
    db.add(refeicao)
    db.commit()
    db.refresh(refeicao)
    return refeicao


def buscar_refeicao(db: Session, refeicao_id: int) -> Refeicao:
    refeicao = db.get(Refeicao, refeicao_id)
    if refeicao is None:
        raise RefeicaoNaoEncontrada
    return refeicao


def atualizar_refeicao(db: Session, refeicao_id: int, dados: RefeicaoUpdate) -> Refeicao:
    refeicao = buscar_refeicao(db, refeicao_id)

    if dados.consumida_em is not None:
        refeicao.consumida_em = _validar_consumida_em(dados.consumida_em)
    if dados.tipo is not None:
        refeicao.tipo = dados.tipo
    if dados.observacao is not None:
        refeicao.observacao = dados.observacao
    if dados.itens is not None:
        # delete-orphan na relacao remove os itens antigos
        refeicao.itens = [ItemRefeicao(**item.model_dump()) for item in dados.itens]

    db.commit()
    db.refresh(refeicao)
    return refeicao


def remover_refeicao(db: Session, refeicao_id: int) -> None:
    db.delete(buscar_refeicao(db, refeicao_id))
    db.commit()


def listar_refeicoes(
    db: Session,
    paciente_id: int,
    dia: date | None = None,
    tipo: TipoRefeicao | None = None,
    limite: int = 50,
    deslocamento: int = 0,
) -> list[Refeicao]:
    """Refeicoes de um paciente, das mais recentes para as mais antigas.

    Com `dia`, restringe ao intervalo daquele dia em UTC. Com `tipo`, restringe
    a uma categoria (cafe da manha, almoco, lanche ou jantar - RF19).
    """
    consulta = select(Refeicao).where(Refeicao.paciente_id == paciente_id)

    if dia is not None:
        inicio, fim = _intervalo_do_dia(dia)
        consulta = consulta.where(Refeicao.consumida_em >= inicio, Refeicao.consumida_em < fim)

    if tipo is not None:
        consulta = consulta.where(Refeicao.tipo == tipo)

    consulta = (
        consulta.order_by(Refeicao.consumida_em.desc(), Refeicao.id.desc())
        .limit(limite)
        .offset(deslocamento)
    )
    return list(db.execute(consulta).scalars())


def consumo_diario(
    db: Session, paciente_id: int, dia: date, tipo: TipoRefeicao | None = None
) -> dict[str, object]:
    """Consumo do dia com os totais de calorias e macros (RF12).

    Com `tipo`, restringe o consumo a uma categoria de refeicao (RF19).
    """
    refeicoes = listar_refeicoes(db, paciente_id, dia=dia, tipo=tipo, limite=200)
    itens = [item for refeicao in refeicoes for item in refeicao.itens]

    totais: dict[str, Decimal] = {campo: somar(itens, campo) for campo in CAMPOS_NUTRICIONAIS}

    return {
        "paciente_id": paciente_id,
        "data": dia,
        "quantidade_refeicoes": len(refeicoes),
        "totais": totais,
        "refeicoes": refeicoes,
    }
