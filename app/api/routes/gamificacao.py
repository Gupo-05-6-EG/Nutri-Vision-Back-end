"""Resgate de ofensiva e catalogo de conquistas do proprio paciente."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update

from app.api.deps import exigir_perfil
from app.db.deps import DbSession
from app.models.paciente import Paciente
from app.models.usuario import Perfil, Usuario
from app.services.conquistas import avaliar_conquistas

router = APIRouter(prefix="/gamificacao", tags=["gamificacao"])
PacienteAtual = Annotated[Usuario, Depends(exigir_perfil(Perfil.PACIENTE))]
CUSTO_BLOQUEIO_XP = 100


@router.get("")
def consultar(db: DbSession, usuario: PacienteAtual) -> dict:
    paciente = db.get(Paciente, usuario.id)
    return {
        "streak": paciente.streak,
        "xp": paciente.xp,
        "bloqueios_perda": paciente.bloqueios_perda,
        "custo_bloqueio_xp": CUSTO_BLOQUEIO_XP,
    }


@router.post("/bloqueios")
def comprar_bloqueio(db: DbSession, usuario: PacienteAtual) -> dict:
    # Debito e credito atomicos: requisicoes concorrentes nao gastam o mesmo XP.
    resultado = db.execute(
        update(Paciente)
        .where(Paciente.id == usuario.id, Paciente.xp >= CUSTO_BLOQUEIO_XP)
        .values(xp=Paciente.xp - CUSTO_BLOQUEIO_XP, bloqueios_perda=Paciente.bloqueios_perda + 1)
    )
    if resultado.rowcount != 1:
        raise HTTPException(409, "XP insuficiente para resgatar o bloqueio")
    db.commit()
    return consultar(db, usuario)


@router.get("/conquistas")
def conquistas(db: DbSession, usuario: PacienteAtual) -> list[dict]:
    paciente = db.scalar(select(Paciente).where(Paciente.id == usuario.id).with_for_update())
    resultado = avaliar_conquistas(db, paciente)
    db.commit()
    return resultado
