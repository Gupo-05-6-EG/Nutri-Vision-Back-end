"""Catálogo e concessão de conquistas no fechamento da ofensiva."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.conquista import ConquistaPaciente
from app.models.paciente import Paciente
from app.models.refeicao import Refeicao


class ConquistaOut(BaseModel):
    codigo: str
    nome: str
    meta: int
    progresso: int
    obtida_em: datetime | None


CATALOGO: tuple[tuple[str, str, Literal["streak", "refeicoes"], int], ...] = (
    ("streak_30", "30 dias de ofensiva", "streak", 30),
    ("refeicoes_100", "100 refeições registradas", "refeicoes", 100),
)


def registrar_conquistas(db: Session, ofensivas: dict[int, int]) -> None:
    """Registra marcos dos pacientes já bloqueados pelo fechamento diário."""
    if not ofensivas:
        return
    contagens = dict(
        db.execute(
            select(Refeicao.paciente_id, func.count())
            .where(Refeicao.paciente_id.in_(ofensivas))
            .group_by(Refeicao.paciente_id)
        ).all()
    )
    obtidas = set(
        db.execute(
            select(ConquistaPaciente.paciente_id, ConquistaPaciente.codigo).where(
                ConquistaPaciente.paciente_id.in_(ofensivas)
            )
        ).all()
    )
    for paciente_id, streak in ofensivas.items():
        progresso = {"streak": streak, "refeicoes": contagens.get(paciente_id, 0)}
        for codigo, _, criterio, meta in CATALOGO:
            if progresso[criterio] >= meta and (paciente_id, codigo) not in obtidas:
                db.add(ConquistaPaciente(paciente_id=paciente_id, codigo=codigo))


def listar_conquistas(db: Session, paciente: Paciente) -> list[ConquistaOut]:
    refeicoes = db.scalar(
        select(func.count()).select_from(Refeicao).where(Refeicao.paciente_id == paciente.id)
    )
    progresso = {"streak": paciente.streak, "refeicoes": refeicoes or 0}
    obtidas = dict(
        db.execute(
            select(ConquistaPaciente.codigo, ConquistaPaciente.obtida_em).where(
                ConquistaPaciente.paciente_id == paciente.id
            )
        ).all()
    )
    resultado = []
    for codigo, nome, criterio, meta in CATALOGO:
        data = obtidas.get(codigo)
        if data is not None and data.tzinfo is None:
            data = data.replace(tzinfo=UTC)
        resultado.append(
            ConquistaOut(
                codigo=codigo,
                nome=nome,
                meta=meta,
                progresso=meta if data else min(progresso[criterio], meta),
                obtida_em=data,
            )
        )
    return resultado
