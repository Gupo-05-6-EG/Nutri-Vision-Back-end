"""Dependencias de autenticacao das rotas (RF13).

Uso numa rota protegida:

    def minha_rota(usuario: UsuarioAtual, db: DbSession): ...

Para restringir a um perfil (ex.: so nutricionista):

    def minha_rota(usuario: Annotated[Usuario, Depends(exigir_perfil(Perfil.NUTRICIONISTA))]): ...

Acesso aos dados de um paciente (Task 1.6, RNF06):

    # le: o proprio paciente ou um nutricionista com vinculo
    def rota(paciente_id: int, acesso: AcessoAoPaciente): ...

    # escreve: so o proprio paciente
    def rota(paciente_id: int, acesso: AcessoPropriaConta): ...

`paciente_id` e lido do caminho ou da query pela propria dependencia. Em rotas em
que ele vem no corpo, use `garantir_acesso_ao_paciente` / `garantir_propria_conta`.
Sem acesso a resposta e sempre 403, exista o paciente ou nao, para a API nao
revelar quais ids existem.
"""

from typing import Annotated

from annotated_types import Gt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import TokenInvalido, ler_token_acesso
from app.db.deps import DbSession
from app.models.usuario import Perfil, Usuario
from app.services import auth as servico
from app.services.vinculos import nutricionista_vinculado

# auto_error=False para responder 401 (e nao o 403 padrao do HTTPBearer) quando
# o header nao vem.
bearer = HTTPBearer(auto_error=False, description="Token JWT devolvido pelo login/cadastro")

NAO_AUTENTICADO = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Nao autenticado",
    headers={"WWW-Authenticate": "Bearer"},
)


def usuario_atual(
    db: DbSession,
    credenciais: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Usuario:
    if credenciais is None:
        raise NAO_AUTENTICADO
    try:
        usuario_id = ler_token_acesso(credenciais.credentials)
    except TokenInvalido:
        raise NAO_AUTENTICADO from None
    usuario = servico.buscar_usuario(db, usuario_id)
    if usuario is None:  # conta removida depois de emitir o token
        raise NAO_AUTENTICADO
    return usuario


UsuarioAtual = Annotated[Usuario, Depends(usuario_atual)]


def exigir_perfil(perfil: Perfil):
    """Dependencia que so deixa passar o usuario autenticado com o perfil dado (403)."""

    def _dependencia(usuario: UsuarioAtual) -> Usuario:
        if usuario.perfil != perfil:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Perfil nao autorizado"
            )
        return usuario

    return _dependencia


ACESSO_NEGADO = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN, detail="Sem acesso aos dados deste paciente"
)


def garantir_propria_conta(usuario: Usuario, paciente_id: int) -> None:
    """So o proprio paciente passa (escrita nos dados dele)."""
    if usuario.perfil != Perfil.PACIENTE or usuario.id != paciente_id:
        raise ACESSO_NEGADO


def garantir_acesso_ao_paciente(db: Session, usuario: Usuario, paciente_id: int) -> None:
    """O proprio paciente, ou um nutricionista com vinculo com ele (leitura)."""
    if usuario.perfil == Perfil.PACIENTE and usuario.id == paciente_id:
        return
    if usuario.perfil == Perfil.NUTRICIONISTA and nutricionista_vinculado(
        db, usuario.id, paciente_id
    ):
        return
    raise ACESSO_NEGADO


# Gt(0) aqui mantem o 422 de id invalido (0, negativo) em vez de virar 403.
PacienteIdValido = Annotated[int, Gt(0)]


def _acesso_ao_paciente(
    paciente_id: PacienteIdValido, usuario: UsuarioAtual, db: DbSession
) -> Usuario:
    garantir_acesso_ao_paciente(db, usuario, paciente_id)
    return usuario


def _acesso_propria_conta(paciente_id: PacienteIdValido, usuario: UsuarioAtual) -> Usuario:
    garantir_propria_conta(usuario, paciente_id)
    return usuario


# `paciente_id` sem Path/Query: o FastAPI le do caminho se ele estiver na URL e da
# query se nao estiver.
AcessoAoPaciente = Annotated[Usuario, Depends(_acesso_ao_paciente)]
AcessoPropriaConta = Annotated[Usuario, Depends(_acesso_propria_conta)]
