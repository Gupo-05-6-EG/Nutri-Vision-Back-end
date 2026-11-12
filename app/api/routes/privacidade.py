"""Endpoints de consentimento e direitos de privacidade do titular."""

from fastapi import APIRouter, HTTPException, Response, status
from fastapi.encoders import jsonable_encoder

from app.api.deps import UsuarioAtual
from app.db.deps import DbSession
from app.models.consentimento import Consentimento
from app.schemas.privacidade import ConsentimentoIn, ConsentimentoOut, ConsentimentoStatusOut
from app.services import privacidade as servico

router = APIRouter(prefix="/privacidade", tags=["privacidade"])


def _consentimento_out(item: Consentimento) -> ConsentimentoOut:
    return ConsentimentoOut(
        versao_termo=item.versao_termo,
        aceito_em=item.aceito_em,
        revogado_em=item.revogado_em,
    )


@router.get("/consentimento", response_model=ConsentimentoStatusOut)
def obter_consentimento(usuario: UsuarioAtual, db: DbSession) -> ConsentimentoStatusOut:
    itens = servico.listar_consentimentos(db, usuario.id)
    return ConsentimentoStatusOut(
        consentimentos=[_consentimento_out(item) for item in itens],
        consentimento_ativo=bool(itens and itens[-1].revogado_em is None),
    )


@router.post(
    "/consentimento",
    response_model=ConsentimentoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Registra o aceite de uma versao do termo",
)
def aceitar_consentimento(
    dados: ConsentimentoIn, usuario: UsuarioAtual, db: DbSession
) -> ConsentimentoOut:
    item = servico.registrar_consentimento(db, usuario.id, dados.versao_termo.strip())
    return _consentimento_out(item)


@router.post("/consentimento/revogar", response_model=ConsentimentoOut)
def revogar_consentimento(usuario: UsuarioAtual, db: DbSession) -> ConsentimentoOut:
    item = servico.revogar_consentimento(db, usuario.id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nenhum consentimento ativo")
    return _consentimento_out(item)


@router.get("/dados", summary="Exporta os dados pessoais do titular")
def exportar_dados(usuario: UsuarioAtual, db: DbSession) -> dict[str, object]:
    return jsonable_encoder(servico.exportar_dados(db, usuario))


@router.delete("/conta", status_code=status.HTTP_204_NO_CONTENT)
def excluir_conta(usuario: UsuarioAtual, db: DbSession) -> Response:
    servico.excluir_conta(db, usuario)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
