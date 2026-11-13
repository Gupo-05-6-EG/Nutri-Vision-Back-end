"""Consulta da ofensiva e resgate de bloqueio pelo próprio paciente."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from app.api.deps import exigir_perfil
from app.db.deps import DbSession
from app.models.paciente import Paciente
from app.models.usuario import Perfil, Usuario
from app.services.gamificacao import CUSTO_BLOQUEIO_XP, resgatar_bloqueio

router = APIRouter(prefix="/gamificacao", tags=["gamificacao"])
PacienteAtual = Annotated[Usuario, Depends(exigir_perfil(Perfil.PACIENTE))]


class OfensivaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    streak: int
    xp: int
    bloqueios_perda: int
    custo_bloqueio_xp: int = CUSTO_BLOQUEIO_XP


@router.get("")
def consultar_ofensiva(db: DbSession, usuario: PacienteAtual) -> OfensivaOut:
    paciente = db.get(Paciente, usuario.id)
    if paciente is None:
        raise HTTPException(404, "Paciente nao encontrado")
    return OfensivaOut.model_validate(paciente)


@router.post("/bloqueios")
def comprar_bloqueio(db: DbSession, usuario: PacienteAtual) -> OfensivaOut:
    paciente = resgatar_bloqueio(db, usuario.id)
    if paciente is None:
        raise HTTPException(409, "XP insuficiente para resgatar o bloqueio")
    return OfensivaOut.model_validate(paciente)
