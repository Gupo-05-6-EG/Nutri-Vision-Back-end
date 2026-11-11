"""Regras de negocio de Gamificacao, Streak, XP e Leaderboard Semanal (RF05, RF16, RF29)."""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.historico_xp import HistoricoXP
from app.models.paciente import Paciente
from app.models.refeicao import ItemRefeicao, Refeicao
from app.schemas.gamificacao import LeaderboardItem, LeaderboardOut
from app.services import amizades as amizades_servico

FUSO_HORARIO = ZoneInfo("America/Sao_Paulo")
PERCENTUAL_MAXIMO_DA_META = Decimal("0.30")
XP_POR_DIA = 50


class GamificacaoError(Exception):
    """Erro base para operacoes de gamificacao."""


class PacienteNaoEncontrado(GamificacaoError):
    """Paciente informado nao existe."""


def _garantir_paciente(db: Session, paciente_id: int) -> Paciente:
    paciente = db.get(Paciente, paciente_id)
    if not paciente:
        raise PacienteNaoEncontrado(f"Paciente {paciente_id} nao encontrado")
    return paciente


def janela_semanal(referencia: datetime | None = None) -> tuple[datetime, datetime]:
    """Calcula limites em UTC da janela semanal vigente (Segunda 00:00 a Domingo 23:59:59)."""
    agora = (referencia or datetime.now(UTC)).astimezone(UTC)
    inicio = (agora - timedelta(days=agora.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    fim = inicio + timedelta(days=6, hours=23, minutes=59, seconds=59, microseconds=999999)
    return inicio, fim


def conceder_xp(db: Session, paciente_id: int, quantidade: int, motivo: str) -> HistoricoXP:
    """Registra ganho de XP para um paciente e atualiza seu saldo total acumulado."""
    paciente = _garantir_paciente(db, paciente_id)

    paciente.xp += quantidade
    registro = HistoricoXP(
        paciente_id=paciente_id,
        quantidade=quantidade,
        motivo=motivo,
        criado_em=datetime.now(UTC),
    )
    db.add(registro)
    db.commit()
    db.refresh(registro)
    return registro


def calcular_xp_semanal(
    db: Session, paciente_ids: list[int], inicio: datetime, fim: datetime
) -> dict[int, int]:
    """Calcula o total de XP obtido por cada paciente na janela temporal especificada."""
    if not paciente_ids:
        return {}

    totais: dict[int, int] = {pid: 0 for pid in paciente_ids}
    consulta = (
        select(
            HistoricoXP.paciente_id,
            func.coalesce(func.sum(HistoricoXP.quantidade), 0).label("total_xp"),
        )
        .where(
            HistoricoXP.paciente_id.in_(paciente_ids),
            HistoricoXP.criado_em >= inicio,
            HistoricoXP.criado_em <= fim,
        )
        .group_by(HistoricoXP.paciente_id)
    )

    linhas = db.execute(consulta).all()
    for row in linhas:
        totais[row.paciente_id] = int(row.total_xp)

    return totais


def obter_leaderboard_semanal(
    db: Session,
    paciente_id: int,
    limite: int = 10,
    referencia: datetime | None = None,
    incluir_solicitante: bool = True,
) -> LeaderboardOut:
    """Retorna o placar ordenado dos amigos por XP semanal (RF05.3, RF29)."""
    _garantir_paciente(db, paciente_id)

    amigo_ids = amizades_servico.obter_ids_amigos_aceitos(db, paciente_id)
    participantes_ids = list(set([paciente_id] + amigo_ids)) if incluir_solicitante else amigo_ids

    inicio, fim = janela_semanal(referencia)

    if not participantes_ids:
        return LeaderboardOut(
            inicio_semana=inicio,
            fim_semana=fim,
            total_participantes=0,
            posicao_solicitante=None,
            ranking=[],
        )

    totais_xp = calcular_xp_semanal(db, participantes_ids, inicio, fim)

    pacientes_consulta = select(Paciente).where(Paciente.id.in_(participantes_ids))
    pacientes = {p.id: p for p in db.scalars(pacientes_consulta).all()}

    # Agrupa candidatos para ordenacao
    candidatos = []
    for pid in participantes_ids:
        paciente = pacientes.get(pid)
        candidatos.append(
            {
                "paciente_id": pid,
                "username": paciente.username if paciente else None,
                "streak": paciente.streak if paciente else 0,
                "xp_semanal": totais_xp.get(pid, 0),
            }
        )

    # Ordenacao: Maior ganho de XP semanal -> Maior streak -> Menor ID
    candidatos.sort(key=lambda c: (-c["xp_semanal"], -c["streak"], c["paciente_id"]))

    posicao_solicitante: int | None = None
    ranking_itens: list[LeaderboardItem] = []

    for idx, c in enumerate(candidatos, start=1):
        if c["paciente_id"] == paciente_id:
            posicao_solicitante = idx

        if idx <= limite:
            ranking_itens.append(
                LeaderboardItem(
                    posicao=idx,
                    paciente_id=c["paciente_id"],
                    username=c["username"],
                    xp_semanal=c["xp_semanal"],
                    streak=c["streak"],
                    e_voce=(c["paciente_id"] == paciente_id),
                )
            )

    return LeaderboardOut(
        inicio_semana=inicio,
        fim_semana=fim,
        total_participantes=len(candidatos),
        posicao_solicitante=posicao_solicitante,
        ranking=ranking_itens,
    )


def listar_historico_xp(
    db: Session, paciente_id: int, limite: int = 50, deslocamento: int = 0
) -> list[HistoricoXP]:
    """Lista eventos individuais de XP concedidos a um paciente."""
    _garantir_paciente(db, paciente_id)
    consulta = (
        select(HistoricoXP)
        .where(HistoricoXP.paciente_id == paciente_id)
        .order_by(HistoricoXP.criado_em.desc())
        .offset(deslocamento)
        .limit(limite)
    )
    return list(db.scalars(consulta).all())


def processar_gamificacao_diaria(db: Session, dia: date) -> int:
    """Atualiza streak/XP para o dia local informado; retorna pacientes processados."""
    inicio_local = datetime.combine(dia, time.min, tzinfo=FUSO_HORARIO)
    fim_local = datetime.combine(dia, time.max, tzinfo=FUSO_HORARIO)
    inicio_utc = inicio_local.astimezone(UTC)
    fim_utc = fim_local.astimezone(UTC)

    consumo = (
        select(
            Refeicao.paciente_id,
            func.count(func.distinct(Refeicao.id)).label("quantidade_refeicoes"),
            func.coalesce(func.sum(ItemRefeicao.calorias_kcal), 0).label("calorias"),
        )
        .select_from(Refeicao)
        .outerjoin(ItemRefeicao, ItemRefeicao.refeicao_id == Refeicao.id)
        .where(Refeicao.consumida_em >= inicio_utc, Refeicao.consumida_em <= fim_utc)
        .group_by(Refeicao.paciente_id)
        .subquery()
    )
    resultados = {
        paciente_id: (quantidade, Decimal(calorias))
        for paciente_id, quantidade, calorias in db.execute(select(consumo)).all()
    }

    pacientes = db.execute(
        select(Paciente).where(
            (Paciente.gamificacao_processada_em.is_(None))
            | (Paciente.gamificacao_processada_em < dia)
        )
    ).scalars()
    processados = 0
    for paciente in pacientes:
        quantidade, calorias = resultados.get(paciente.id, (0, Decimal(0)))
        cumpriu_meta = (
            paciente.meta_kcal is not None
            and quantidade >= 2
            and calorias <= paciente.meta_kcal * PERCENTUAL_MAXIMO_DA_META
        )
        if cumpriu_meta:
            paciente.streak += 1
            paciente.xp += XP_POR_DIA
        else:
            paciente.streak = 0
        paciente.gamificacao_processada_em = dia
        processados += 1

    db.commit()
    return processados


def hoje_local() -> date:
    """Data corrente no fuso oficial usado pelo processamento diário."""
    return datetime.now(FUSO_HORARIO).date()
