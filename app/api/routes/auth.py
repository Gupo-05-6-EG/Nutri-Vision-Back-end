"""Endpoints de cadastro e login (RF13).

Cadastro e login devolvem o mesmo `TokenOut`, entao o app ja sai do cadastro
logado e segue direto para a triagem.
"""

from fastapi import APIRouter, HTTPException, status

from app.api.deps import UsuarioAtual
from app.core.security import criar_token_acesso
from app.db.deps import DbSession
from app.models.usuario import Usuario
from app.schemas.auth import (
    CadastroNutricionistaIn,
    CadastroPacienteIn,
    LoginIn,
    TokenOut,
    UsuarioOut,
)
from app.services import auth as servico

router = APIRouter(prefix="/auth", tags=["auth"])

EMAIL_EM_USO = HTTPException(status.HTTP_409_CONFLICT, "Email ja cadastrado")


def _usuario_out(db: DbSession, usuario: Usuario) -> UsuarioOut:
    return UsuarioOut.model_validate(usuario).model_copy(
        update={"crn": servico.crn_do_usuario(db, usuario)}
    )


def _token(db: DbSession, usuario: Usuario) -> TokenOut:
    token, expira_em = criar_token_acesso(usuario.id, usuario.perfil)
    return TokenOut(access_token=token, expira_em=expira_em, usuario=_usuario_out(db, usuario))


@router.post(
    "/cadastro/paciente",
    response_model=TokenOut,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra um paciente e devolve o token de acesso",
)
def cadastrar_paciente(dados: CadastroPacienteIn, db: DbSession) -> TokenOut:
    try:
        usuario = servico.cadastrar_paciente(db, dados)
    except servico.EmailJaCadastrado:
        raise EMAIL_EM_USO from None
    return _token(db, usuario)


@router.post(
    "/cadastro/nutricionista",
    response_model=TokenOut,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra um nutricionista e devolve o token de acesso",
)
def cadastrar_nutricionista(dados: CadastroNutricionistaIn, db: DbSession) -> TokenOut:
    try:
        usuario = servico.cadastrar_nutricionista(db, dados)
    except servico.EmailJaCadastrado:
        raise EMAIL_EM_USO from None
    except servico.CrnJaCadastrado:
        raise HTTPException(status.HTTP_409_CONFLICT, "CRN ja cadastrado") from None
    return _token(db, usuario)


@router.post("/login", response_model=TokenOut, summary="Login com email e senha")
def login(dados: LoginIn, db: DbSession) -> TokenOut:
    try:
        usuario = servico.autenticar(db, dados.email, dados.senha)
    except servico.CredenciaisInvalidas:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Email ou senha invalidos",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    return _token(db, usuario)


@router.get("/me", response_model=UsuarioOut, summary="Dados do usuario do token")
def me(usuario: UsuarioAtual, db: DbSession) -> UsuarioOut:
    return _usuario_out(db, usuario)
