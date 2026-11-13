"""PDF de evolucao disponivel apenas para nutricionista com vinculo ativo."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response

from app.api.deps import exigir_perfil, garantir_acesso_ao_paciente
from app.db.deps import DbSession
from app.models.usuario import Perfil, Usuario
from app.services.relatorios import gerar_relatorio

router = APIRouter(tags=["relatorios"])


@router.get(
    "/pacientes/{paciente_id}/relatorio.pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
    summary="Exporta consumo, macros e meta do periodo em PDF",
)
def relatorio(
    paciente_id: int,
    inicio: date,
    fim: date,
    db: DbSession,
    usuario: Annotated[Usuario, Depends(exigir_perfil(Perfil.NUTRICIONISTA))],
) -> Response:
    garantir_acesso_ao_paciente(db, usuario, paciente_id)
    if fim < inicio or (fim - inicio).days > 89 or fim == date.max or inicio == date.min:
        raise HTTPException(422, "Informe um periodo de 1 a 90 dias")
    return Response(
        gerar_relatorio(db, paciente_id, inicio, fim),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="evolucao-{paciente_id}.pdf"',
            "Cache-Control": "no-store",
        },
    )
