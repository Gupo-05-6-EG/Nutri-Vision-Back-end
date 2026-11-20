"""Endpoints de regras e alertas de desvio de meta para o nutricionista (Task 5.4, RF10.2)."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.api.deps import exigir_perfil
from app.core.tempo import hoje_local
from app.db.deps import DbSession
from app.models.usuario import Perfil, Usuario
from app.schemas.alerta_desvio import (
    AlertaDesvioOut,
    ProcessamentoAlertasOut,
    RegraAlertaDesvioIn,
    RegraAlertaDesvioOut,
)
from app.services import alertas_desvio as servico

router = APIRouter(prefix="/alertas-desvio", tags=["alertas-desvio"])

NutricionistaAutenticado = Annotated[Usuario, Depends(exigir_perfil(Perfil.NUTRICIONISTA))]
AlertaId = Annotated[int, Path(gt=0, description="Id do alerta de desvio")]


@router.get(
    "/regra",
    response_model=RegraAlertaDesvioOut,
    summary="Consulta a regra configuravel de alerta de desvio do nutricionista",
)
def obter_regra(
    db: DbSession,
    nutricionista: NutricionistaAutenticado,
) -> RegraAlertaDesvioOut:
    return servico.obter_regra(db, nutricionista.id)


@router.put(
    "/regra",
    response_model=RegraAlertaDesvioOut,
    summary="Salva a regra configuravel de alerta de desvio (ex.: >20% por 3 dias)",
)
def salvar_regra(
    dados: RegraAlertaDesvioIn,
    db: DbSession,
    nutricionista: NutricionistaAutenticado,
) -> RegraAlertaDesvioOut:
    return servico.salvar_regra(db, nutricionista.id, dados)


@router.get(
    "",
    response_model=list[AlertaDesvioOut],
    summary="Lista os alertas de desvio significativo do plano dos pacientes vinculados",
)
def listar_alertas(
    db: DbSession,
    nutricionista: NutricionistaAutenticado,
    paciente_id: Annotated[int | None, Query(gt=0)] = None,
    apenas_nao_lidos: Annotated[bool, Query()] = False,
) -> list[AlertaDesvioOut]:
    return servico.listar_alertas(
        db,
        nutricionista.id,
        paciente_id=paciente_id,
        apenas_nao_lidos=apenas_nao_lidos,
    )


@router.post(
    "/processar",
    response_model=ProcessamentoAlertasOut,
    summary="Avalia desvios de meta para os pacientes vinculados ao nutricionista",
)
def processar_alertas(
    db: DbSession,
    nutricionista: NutricionistaAutenticado,
    dia_referencia: Annotated[date | None, Query()] = None,
) -> ProcessamentoAlertasOut:
    dia = dia_referencia or hoje_local()
    gerados = servico.processar_alertas_desvio_diario(
        db,
        dia,
        nutricionista_id=nutricionista.id,
    )
    return ProcessamentoAlertasOut(data_referencia=dia, alertas_gerados=gerados)


@router.patch(
    "/{alerta_id}/lido",
    response_model=AlertaDesvioOut,
    summary="Marca uma notificacao de alerta de desvio como lida",
)
def marcar_como_lido(
    alerta_id: AlertaId,
    db: DbSession,
    nutricionista: NutricionistaAutenticado,
) -> AlertaDesvioOut:
    try:
        return servico.marcar_alerta_como_lido(db, nutricionista.id, alerta_id)
    except servico.AlertaNaoEncontrado:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alerta de desvio nao encontrado") from None
