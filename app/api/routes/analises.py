"""Analise de fotos de refeicoes pela IA (RF02, RF03).

O back-end repassa a foto ao servico de IA (Nutri-Vision-IA) e devolve o
resultado ja ligado a nossa tabela TACO, com kcal e macros das gramas
estimadas. A analise e assincrona:

1. `POST /analises` com a foto -> `id` (status `QUEUED`, ou `NOT_ESTIMATED` na
   hora se a foto estiver borrada ou mal iluminada);
2. `GET /analises/{id}` ate o status sair de `QUEUED`/`PROCESSING`.

Nada e gravado aqui: o paciente revisa os itens e registra a refeicao em
`POST /refeicoes`. A foto nao e guardada em lugar nenhum, e o resultado expira
no servico de IA depois de 24 h. So pacientes analisam fotos.
"""

from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Path, UploadFile, status

from app.api.deps import exigir_perfil
from app.core.config import get_settings
from app.db.deps import DbSession
from app.models.usuario import Perfil, Usuario
from app.schemas.analise_ia import AnaliseCriadaOut, AnaliseOut
from app.services import analise_ia, ia_cliente

router = APIRouter(prefix="/analises", tags=["analises"])

PacienteAtual = Annotated[Usuario, Depends(exigir_perfil(Perfil.PACIENTE))]
ClienteIA = Annotated[httpx.Client, Depends(ia_cliente.get_cliente_ia)]

IA_INDISPONIVEL = HTTPException(
    status.HTTP_503_SERVICE_UNAVAILABLE, "Servico de analise indisponivel, tente novamente"
)


def _ler_foto(foto: UploadFile) -> bytes:
    if not (foto.content_type or "").startswith("image/"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Envie uma imagem")
    limite = get_settings().AI_MAX_UPLOAD_BYTES
    conteudo = foto.file.read(limite + 1)
    if not conteudo:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Arquivo vazio")
    if len(conteudo) > limite:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"Imagem maior que {limite} bytes"
        )
    return conteudo


@router.post(
    "",
    response_model=AnaliseCriadaOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Envia a foto do prato para a IA analisar",
)
def enviar_foto(
    _paciente: PacienteAtual,
    cliente: ClienteIA,
    file: Annotated[UploadFile, File(description="Foto da refeicao (JPEG, PNG, WebP, HEIC...)")],
) -> AnaliseCriadaOut:
    conteudo = _ler_foto(file)
    try:
        analise = ia_cliente.enviar_foto(
            cliente, conteudo, file.filename or "foto", file.content_type or "image/jpeg"
        )
    except ia_cliente.FotoRecusada as erro:
        raise HTTPException(erro.status_code, erro.detalhe) from None
    except ia_cliente.ServicoIAIndisponivel:
        raise IA_INDISPONIVEL from None
    return AnaliseCriadaOut(
        id=analise["id"],
        status=analise["status"],
        motivo=analise.get("reason"),
        problemas=analise.get("issues"),
    )


@router.get(
    "/{analise_id}",
    response_model=AnaliseOut,
    summary="Andamento e resultado da analise, com os alimentos da TACO e as macros",
)
def consultar_analise(
    analise_id: Annotated[UUID, Path(description="Id devolvido por `POST /analises`")],
    db: DbSession,
    _paciente: PacienteAtual,
    cliente: ClienteIA,
) -> AnaliseOut:
    try:
        analise = ia_cliente.consultar_analise(cliente, analise_id)
    except ia_cliente.AnaliseNaoEncontrada:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Analise nao encontrada ou expirada (24 h)"
        ) from None
    except ia_cliente.ServicoIAIndisponivel:
        raise IA_INDISPONIVEL from None
    return AnaliseOut.model_validate(analise_ia.montar_resultado(db, analise))
