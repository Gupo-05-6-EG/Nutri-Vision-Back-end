"""Endpoints do paciente: triagem e calculo basal (RF14) e incentivo do nutricionista.

O paciente precisa ter se cadastrado antes (`POST /auth/cadastro/paciente`).
Exige token e so o proprio paciente pode registrar a sua triagem (Task 1.6, RNF06).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel

from app.api.deps import AcessoPropriaConta, exigir_perfil, garantir_acesso_ao_paciente
from app.db.deps import DbSession
from app.models.usuario import Perfil, Usuario
from app.schemas.paciente import TetoCaloricoOut, TriagemIn
from app.services import gamificacao
from app.services import pacientes as servico

router = APIRouter(prefix="/pacientes", tags=["pacientes"])

PacienteId = Annotated[int, Path(gt=0, description="Id do paciente")]


@router.post(
    "/{paciente_id}/triagem",
    response_model=TetoCaloricoOut,
    summary="Recebe a triagem e gera o teto calorico diario inicial (Harris-Benedict)",
)
def registrar_triagem(
    paciente_id: PacienteId, dados: TriagemIn, db: DbSession, paciente: AcessoPropriaConta
) -> TetoCaloricoOut:
    try:
        resultado = servico.registrar_triagem(db, paciente_id, dados, autor_id=paciente.id)
    except servico.PacienteNaoEncontrado:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente nao encontrado") from None
    return TetoCaloricoOut.model_validate(resultado)


NutricionistaAtual = Annotated[Usuario, Depends(exigir_perfil(Perfil.NUTRICIONISTA))]


class IncentivoOut(BaseModel):
    paciente_id: int
    xp_concedido: int
    xp_total: int


@router.post(
    "/{paciente_id}/incentivo",
    response_model=IncentivoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Nutricionista vinculado da um incentivo de +10 XP (uma vez por dia)",
    responses={409: {"description": "O paciente ja recebeu o incentivo hoje"}},
)
def dar_incentivo(
    paciente_id: PacienteId, db: DbSession, nutricionista: NutricionistaAtual
) -> IncentivoOut:
    garantir_acesso_ao_paciente(db, nutricionista, paciente_id)
    try:
        paciente = gamificacao.conceder_incentivo(db, paciente_id)
    except gamificacao.IncentivoJaConcedido:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "O paciente ja recebeu o incentivo hoje"
        ) from None
    return IncentivoOut(
        paciente_id=paciente.id, xp_concedido=gamificacao.XP_INCENTIVO, xp_total=paciente.xp
    )
