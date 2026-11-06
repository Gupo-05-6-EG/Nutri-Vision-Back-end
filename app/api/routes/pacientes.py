"""Endpoint de triagem e calculo basal (RF14).

O paciente precisa ter se cadastrado antes (`POST /auth/cadastro/paciente`).
`paciente_id` ainda chega no caminho: a Task 1.6 (RNF06) passa a exigir o token
e a validar se quem chama e o proprio paciente ou um nutricionista vinculado.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, status

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
    try:
        resultado = servico.registrar_triagem(db, paciente_id, dados)
    except servico.PacienteNaoEncontrado:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente nao encontrado") from None
    return TetoCaloricoOut.model_validate(resultado)
