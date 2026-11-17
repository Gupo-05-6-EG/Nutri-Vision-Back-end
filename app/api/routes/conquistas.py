"""Catálogo e progresso de conquistas do próprio paciente."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import exigir_perfil
from app.db.deps import DbSession
from app.models.paciente import Paciente
from app.models.usuario import Perfil, Usuario
from app.services.conquistas import ConquistaOut, listar_conquistas

router = APIRouter(prefix="/gamificacao", tags=["gamificacao"])
PacienteAtual = Annotated[Usuario, Depends(exigir_perfil(Perfil.PACIENTE))]


@router.get("/conquistas")
def consultar_conquistas(db: DbSession, usuario: PacienteAtual) -> list[ConquistaOut]:
    paciente = db.get(Paciente, usuario.id)
    if paciente is None:
        raise HTTPException(404, "Paciente nao encontrado")
    return listar_conquistas(db, paciente)
