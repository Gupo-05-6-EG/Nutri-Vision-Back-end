"""Regras de negocio das refeicoes (RF04, RF12, RF19) e da sincronizacao em lote (RNF07)."""

from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tempo import em_fuso_local, intervalo_do_dia
from app.models.paciente import Paciente
from app.models.refeicao import CAMPOS_NUTRICIONAIS, ItemRefeicao, Refeicao, TipoRefeicao, somar
from app.schemas.refeicao import ItemRefeicaoCreate, RefeicaoCreate, RefeicaoUpdate
from app.services.gamificacao import xp_por_refeicao

# Janelas de horario (hora local, no fuso oficial - ver app/core/tempo.py) usadas
# para sugerir o tipo quando o cliente nao informa um.
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


class RefeicaoInvalidaNoLote(Exception):
    """Uma refeicao do lote nao pode ser gravada; nenhuma refeicao do lote e gravada."""

    def __init__(self, indice: int, campo: str, motivo: str) -> None:
        super().__init__(f"refeicoes[{indice}].{campo} {motivo}")
        self.indice = indice
        self.campo = campo
        self.motivo = motivo


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
    hora = em_fuso_local(consumida_em).hour
    for inicio, fim, tipo in _JANELAS_SUGESTAO:
        if inicio <= hora < fim:
            return tipo
    return TipoRefeicao.LANCHE


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
    xp_por_refeicao(db, refeicao, por_foto=dados.origem == "foto")
    db.commit()
    db.refresh(refeicao)
    return refeicao


_CENTAVO = Decimal("0.01")

# Identidade de uma refeicao para fins de deduplicacao (ver `_impressao`).
Impressao = tuple[int, datetime, str, str | None, tuple[tuple[object, ...], ...]]


def _impressao(
    paciente_id: int,
    consumida_em: datetime,
    tipo: str,
    observacao: str | None,
    itens: Iterable[ItemRefeicao | ItemRefeicaoCreate],
) -> Impressao:
    """Impressao digital de uma refeicao, usada para reconhecer reenvios (RNF07).

    Duas refeicoes sao a mesma quando tem o mesmo paciente, instante (em UTC),
    tipo, observacao e o mesmo conjunto de itens - a ordem dos itens nao
    importa. Serve tanto para o que chega na requisicao quanto para o que ja
    esta no banco (a observacao cifrada ja vem decifrada pelo `TextoCifrado`).
    """
    observacao_normalizada = (observacao or "").strip() or None
    chaves_itens = sorted(
        (
            item.nome_alimento.strip(),
            *(
                Decimal(getattr(item, campo)).quantize(_CENTAVO)
                for campo in ("quantidade_g", *CAMPOS_NUTRICIONAIS)
            ),
        )
        for item in itens
    )
    return (
        paciente_id,
        _em_utc(consumida_em),
        str(tipo),
        observacao_normalizada,
        tuple(chaves_itens),
    )


def criar_refeicoes_em_lote(
    db: Session, paciente_id: int, refeicoes: Sequence[RefeicaoCreate]
) -> list[tuple[Refeicao, bool]]:
    """Grava um lote de refeicoes feitas offline, sem duplicar reenvios (RNF07).

    Devolve, na mesma ordem do lote, cada refeicao e se ela ja existia
    (`True`) ou foi criada agora (`False`). Uma refeicao repetida - ja gravada
    antes ou repetida dentro do proprio lote - devolve a que ja existe.

    E tudo ou nada: o lote inteiro e validado antes de gravar, e qualquer
    refeicao invalida levanta `RefeicaoInvalidaNoLote` sem gravar nenhuma.
    """
    if db.get(Paciente, paciente_id) is None:
        raise PacienteNaoEncontrado

    preparadas: list[tuple[RefeicaoCreate, datetime, str]] = []
    for indice, dados in enumerate(refeicoes):
        if dados.paciente_id != paciente_id:
            raise RefeicaoInvalidaNoLote(indice, "paciente_id", "difere do paciente_id do lote")
        try:
            consumida_em = _validar_consumida_em(dados.consumida_em)
        except DataDeConsumoNoFuturo:
            raise RefeicaoInvalidaNoLote(
                indice, "consumida_em", "nao pode estar no futuro"
            ) from None
        tipo = dados.tipo or sugerir_tipo(consumida_em)
        preparadas.append((dados, consumida_em, str(tipo)))

    # Uma consulta so: as refeicoes do paciente na janela de tempo do lote.
    instantes = [consumida_em for _, consumida_em, _ in preparadas]
    existentes = db.execute(
        select(Refeicao).where(
            Refeicao.paciente_id == paciente_id,
            Refeicao.consumida_em >= min(instantes),
            Refeicao.consumida_em <= max(instantes),
        )
    ).scalars()
    conhecidas: dict[Impressao, Refeicao] = {}
    for refeicao in existentes:
        chave = _impressao(
            paciente_id, refeicao.consumida_em, refeicao.tipo, refeicao.observacao, refeicao.itens
        )
        conhecidas.setdefault(chave, refeicao)

    resultado: list[tuple[Refeicao, bool]] = []
    novas: list[Refeicao] = []
    for dados, consumida_em, tipo in preparadas:
        chave = _impressao(paciente_id, consumida_em, tipo, dados.observacao, dados.itens)
        if chave in conhecidas:
            resultado.append((conhecidas[chave], True))
            continue
        refeicao = Refeicao(
            paciente_id=paciente_id,
            consumida_em=consumida_em,
            tipo=tipo,
            observacao=dados.observacao,
            itens=[ItemRefeicao(**item.model_dump()) for item in dados.itens],
        )
        db.add(refeicao)
        xp_por_refeicao(db, refeicao, por_foto=dados.origem == "foto")
        conhecidas[chave] = refeicao
        novas.append(refeicao)
        resultado.append((refeicao, False))

    db.commit()
    for refeicao in novas:
        db.refresh(refeicao)
    return resultado


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
        inicio, fim = intervalo_do_dia(dia)
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
