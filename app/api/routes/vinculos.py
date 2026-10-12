"""Endpoints do fluxo de vinculacao (Task 1.4)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import Perfil, UsuarioAutenticado, require_perfil
from app.db.deps import DbSession
from app.schemas.vinculo import (
    CodigoVinculacaoCreateOut,
    CodigoVinculacaoIn,
    VinculoCriadoOut,
)
from app.services import vinculos as servico

router = APIRouter(tags=["vinculos"])

NutricionistaAutenticado = Annotated[
    UsuarioAutenticado, Depends(require_perfil(Perfil.NUTRICIONISTA))
]
PacienteAutenticado = Annotated[
    UsuarioAutenticado, Depends(require_perfil(Perfil.PACIENTE))
]


@router.post(
    "/linking-code",
    response_model=CodigoVinculacaoCreateOut,
    summary="Gera um codigo de vinculacao de 6 digitos para o nutricionista autenticado",
)
def gerar_codigo(
    db: DbSession,
    usuario: NutricionistaAutenticado,
) -> CodigoVinculacaoCreateOut:
    try:
        registro = servico.gerar_codigo_vinculacao(db, usuario)
    except servico.PerfilIncompativel:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Perfil nao autorizado",
        ) from None

    return CodigoVinculacaoCreateOut.model_validate(
        {
            "codigo": getattr(registro, "codigo_em_texto"),
            "status": registro.status,
            "expira_em": registro.expira_em,
        }
    )


@router.post(
    "/link",
    response_model=VinculoCriadoOut,
    summary="Resgata um codigo de vinculacao e cria o vinculo do paciente com o nutricionista",
)
def resgatar_codigo(
    dados: CodigoVinculacaoIn,
    db: DbSession,
    usuario: PacienteAutenticado,
) -> VinculoCriadoOut:
    try:
        vinculo = servico.resgatar_codigo_vinculacao(db, usuario, dados.codigo)
    except servico.CodigoVinculacaoNaoEncontrado:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Codigo nao encontrado",
        ) from None
    except servico.CodigoVinculacaoExpirado:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Codigo expirado",
        ) from None
    except servico.CodigoVinculacaoJaUtilizado:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Codigo ja utilizado",
        ) from None
    except servico.PerfilIncompativel:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Perfil nao autorizado",
        ) from None
    except servico.VinculoDuplicado:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Vinculo duplicado",
        ) from None

    return VinculoCriadoOut.model_validate(
        {
            "nutricionista": {
                "id": vinculo.nutricionista_id,
                "nome": vinculo.nutricionista_nome,
                "foto_url": vinculo.nutricionista_foto_url,
            },
            "vinculado_em": vinculo.vinculado_em,
        }
    )