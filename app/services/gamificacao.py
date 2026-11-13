"""Processamento diario de streak e XP (RF16)."""

from datetime import UTC, date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.paciente import Paciente
from app.models.refeicao import ItemRefeicao, Refeicao

FUSO_HORARIO = ZoneInfo("America/Sao_Paulo")
PERCENTUAL_MAXIMO_DA_META = Decimal("0.30")
XP_POR_DIA = 50
CUSTO_BLOQUEIO_XP = 100


def resgatar_bloqueio(db: Session, paciente_id: int) -> Paciente | None:
    """Debita XP e credita um bloqueio em uma única atualização."""
    paciente = db.scalar(
        update(Paciente)
        .where(Paciente.id == paciente_id, Paciente.xp >= CUSTO_BLOQUEIO_XP)
        .values(xp=Paciente.xp - CUSTO_BLOQUEIO_XP, bloqueios_perda=Paciente.bloqueios_perda + 1)
        .returning(Paciente)
    )
    if paciente is not None:
        db.commit()
    return paciente


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
        select(Paciente)
        .where(
            (Paciente.gamificacao_processada_em.is_(None))
            | (Paciente.gamificacao_processada_em < dia)
        )
        .order_by(Paciente.id)
        .with_for_update()
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
        elif paciente.streak > 0 and paciente.bloqueios_perda > 0:
            paciente.bloqueios_perda -= 1
        else:
            paciente.streak = 0
        paciente.gamificacao_processada_em = dia
        processados += 1

    db.commit()
    return processados


def hoje_local() -> date:
    """Data corrente no fuso oficial usado pelo processamento diário."""
    return datetime.now(FUSO_HORARIO).date()
