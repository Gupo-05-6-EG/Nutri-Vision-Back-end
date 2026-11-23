"""Endpoints do fluxo de vinculacao (Task 1.4)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.api.deps import exigir_perfil
from app.db.deps import DbSession
from app.models.usuario import Perfil, Usuario
from app.schemas.vinculo import (
    CodigoVinculacaoCreateOut,
    CodigoVinculacaoIn,
    NutricionistaPublicoOut,
    PacienteVinculadoOut,
    PreviaCodigoOut,
    StatusVinculoOut,
    VinculoCriadoOut,
)
from app.services import vinculos as servico

router = APIRouter(tags=["vinculos"])

NutricionistaAutenticado = Annotated[Usuario, Depends(exigir_perfil(Perfil.NUTRICIONISTA))]
PacienteAutenticado = Annotated[Usuario, Depends(exigir_perfil(Perfil.PACIENTE))]


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
            "codigo": registro.codigo_em_texto,
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
            "status": vinculo.status,
        }
    )


def _resposta_status(vinculo) -> StatusVinculoOut:
    return StatusVinculoOut(
        vinculo_id=vinculo.id,
        paciente_id=vinculo.paciente_id,
        nutricionista_id=vinculo.nutricionista_id,
        status=vinculo.status,
    )


@router.post("/link/{nutricionista_id}/aceitar", response_model=StatusVinculoOut)
def aceitar_vinculo(
    nutricionista_id: int, db: DbSession, usuario: PacienteAutenticado
) -> StatusVinculoOut:
    return _responder_vinculo(db, usuario, nutricionista_id, aceitar=True)


@router.post("/link/{nutricionista_id}/recusar", response_model=StatusVinculoOut)
def recusar_vinculo(
    nutricionista_id: int, db: DbSession, usuario: PacienteAutenticado
) -> StatusVinculoOut:
    return _responder_vinculo(db, usuario, nutricionista_id, aceitar=False)


def _responder_vinculo(db, usuario, nutricionista_id: int, *, aceitar: bool) -> StatusVinculoOut:
    try:
        vinculo = servico.responder_solicitacao(db, usuario, nutricionista_id, aceitar)
    except servico.VinculoNaoEncontrado:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vinculo nao encontrado") from None
    except servico.TransicaoVinculoInvalida:
        raise HTTPException(status.HTTP_409_CONFLICT, "Vinculo nao esta pendente") from None
    return _resposta_status(vinculo)


@router.get(
    "/linking-code/{codigo}/previa",
    response_model=PreviaCodigoOut,
    summary="Mostra quem gerou um codigo valido, antes de o paciente criar a conta",
    responses={404: {"description": "Codigo inexistente, expirado ou ja usado"}},
)
def previa_do_codigo(
    db: DbSession,
    codigo: Annotated[str, Path(pattern=r"^\d{6}$", description="Codigo de 6 digitos")],
) -> PreviaCodigoOut:
    """Publica de proposito: o paciente ainda nao tem conta quando digita o codigo.

    Devolve so o nome e o CRN do profissional (dados publicos de registro), nada
    do paciente. Codigos expiram (LINKING_CODE_EXPIRE_MINUTES) e qualquer
    codigo invalido responde o mesmo 404.
    """
    previa = servico.previa_do_codigo(db, codigo)
    if previa is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Codigo invalido ou expirado")
    registro, nutricionista = previa
    return PreviaCodigoOut(
        nutricionista=NutricionistaPublicoOut(
            id=registro.nutricionista_id,
            nome=registro.nutricionista_nome,
            foto_url=registro.nutricionista_foto_url,
        ),
        crn=nutricionista.crn,
        expira_em=registro.expira_em,
    )


@router.get("/patients", response_model=list[PacienteVinculadoOut])
def listar_pacientes_vinculados(
    db: DbSession,
    usuario: NutricionistaAutenticado,
    busca: str | None = Query(default=None, max_length=120),
    status_vinculo: Literal["ativo", "pendente", "todos"] = Query(
        default="ativo",
        alias="status",
        description="ativo (padrao), pendente (resgatou o codigo e nao aceitou) ou todos",
    ),
) -> list[PacienteVinculadoOut]:
    return [
        PacienteVinculadoOut(
            paciente_id=paciente.id,
            nome=paciente.nome,
            email=paciente.email,
            status=vinculo.status,
            vinculado_em=vinculo.criado_em,
        )
        for vinculo, paciente in servico.listar_pacientes(db, usuario, busca, status_vinculo)
    ]


@router.delete("/patients/{paciente_id}", response_model=StatusVinculoOut)
def desvincular_paciente(
    paciente_id: int, db: DbSession, usuario: NutricionistaAutenticado
) -> StatusVinculoOut:
    try:
        vinculo = servico.encerrar_vinculo(db, usuario, paciente_id)
    except servico.VinculoNaoEncontrado:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vinculo ativo nao encontrado") from None
    return _resposta_status(vinculo)
