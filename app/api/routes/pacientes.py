"""Endpoint de triagem e calculo basal (RF14).

`paciente_id` chega no caminho enquanto nao existe autenticacao. A Task 1.2
passa a tirar o paciente do token JWT e a Task 1.6 aplica o controle de acesso
por perfil e vinculo.
"""

from typing import Annotated

from fastapi import APIRouter, Path

from app.db.deps import DbSession
from app.schemas.paciente import TetoCaloricoOut, TriagemIn
from app.services import pacientes as servico

router = APIRouter(prefix="/pacientes", tags=["pacientes"])

PacienteId = Annotated[int, Path(gt=0, description="Id do paciente")]


@router.post(
    "/{paciente_id}/triagem",
    response_model=TetoCaloricoOut,
    summary="Recebe a triagem e gera o teto calorico diario inicial (Harris-Benedict)",
)
def registrar_triagem(paciente_id: PacienteId, dados: TriagemIn, db: DbSession) -> TetoCaloricoOut:
    return TetoCaloricoOut.model_validate(servico.registrar_triagem(db, paciente_id, dados))
