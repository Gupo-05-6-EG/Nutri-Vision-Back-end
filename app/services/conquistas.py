"""Catalogo e concessao idempotente de conquistas (RF05.6)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.conquista import ConquistaPaciente
from app.models.paciente import Paciente
from app.models.refeicao import Refeicao

CATALOGO = (
    ("streak_7", "Uma semana de constancia", "streak", 7),
    ("streak_30", "30 dias de ofensiva", "streak", 30),
    ("refeicoes_100", "100 refeicoes registradas", "refeicoes", 100),
)


def avaliar_conquistas(db: Session, paciente: Paciente) -> list[dict]:
    refeicoes = (
        db.scalar(
            select(func.count()).select_from(Refeicao).where(Refeicao.paciente_id == paciente.id)
        )
        or 0
    )
    obtidas = {
        c.codigo: c
        for c in db.scalars(
            select(ConquistaPaciente).where(ConquistaPaciente.paciente_id == paciente.id)
        )
    }
    resultado = []
    for codigo, nome, tipo, meta in CATALOGO:
        progresso = paciente.streak if tipo == "streak" else refeicoes
        if progresso >= meta and codigo not in obtidas:
            conquista = ConquistaPaciente(paciente_id=paciente.id, codigo=codigo)
            db.add(conquista)
            db.flush()
            obtidas[codigo] = conquista
        conquista = obtidas.get(codigo)
        resultado.append(
            {
                "codigo": codigo,
                "nome": nome,
                "meta": meta,
                "progresso": meta if conquista else min(progresso, meta),
                "obtida_em": conquista.obtida_em if conquista else None,
            }
        )
    return resultado
