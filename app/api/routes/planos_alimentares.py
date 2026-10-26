"""Endpoints do plano alimentar (RF09.1).

Exigem o token do login. So o nutricionista vinculado ao paciente prescreve;
o plano ativo pode ser lido por ele ou pelo proprio paciente (Task 2.9).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status

from app.api.deps import UsuarioAtual, exigir_perfil
from app.db.deps import DbSession
from app.models.usuario import Perfil, Usuario
from app.schemas.plano_alimentar import PlanoAlimentarIn, PlanoAlimentarOut
from app.services import planos_alimentares as servico

router = APIRouter(prefix="/pacientes", tags=["planos-alimentares"])

PacienteId = Annotated[int, Path(gt=0, description="Id do paciente")]
NutricionistaAutenticado = Annotated[Usuario, Depends(exigir_perfil(Perfil.NUTRICIONISTA))]


def _erro_de_acesso(erro: Exception) -> HTTPException:
    if isinstance(erro, servico.PacienteNaoEncontrado):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Paciente nao encontrado")
    return HTTPException(status.HTTP_403_FORBIDDEN, "Sem vinculo com este paciente")


@router.post(
    "/{paciente_id}/planos",
    response_model=PlanoAlimentarOut,
    status_code=status.HTTP_201_CREATED,
    summary="Prescreve um plano alimentar e o torna o plano ativo do paciente",
)
def prescrever_plano(
    paciente_id: PacienteId,
    dados: PlanoAlimentarIn,
    db: DbSession,
    nutricionista: NutricionistaAutenticado,
) -> PlanoAlimentarOut:
    try:
        plano = servico.prescrever_plano(db, nutricionista, paciente_id, dados)
    except (servico.PacienteNaoEncontrado, servico.AcessoNegado) as erro:
        raise _erro_de_acesso(erro) from None
    except servico.AlimentoTacoNaoEncontrado:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "alimento_taco_id nao existe na TACO"
        ) from None
    return PlanoAlimentarOut.model_validate(plano)


@router.get(
    "/{paciente_id}/planos/ativo",
    response_model=PlanoAlimentarOut,
    summary="Plano alimentar ativo do paciente",
)
def plano_ativo(paciente_id: PacienteId, db: DbSession, usuario: UsuarioAtual) -> PlanoAlimentarOut:
    try:
        plano = servico.plano_ativo(db, usuario, paciente_id)
    except (servico.PacienteNaoEncontrado, servico.AcessoNegado) as erro:
        raise _erro_de_acesso(erro) from None
    except servico.PlanoNaoEncontrado:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente sem plano ativo") from None
    return PlanoAlimentarOut.model_validate(plano)
