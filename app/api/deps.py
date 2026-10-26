"""Dependencias de autenticacao das rotas (RF13).

Uso numa rota protegida:

    def minha_rota(usuario: UsuarioAtual, db: DbSession): ...

Para restringir a um perfil (ex.: so nutricionista):

    def minha_rota(usuario: Annotated[Usuario, Depends(exigir_perfil(Perfil.NUTRICIONISTA))]): ...

A regra de quem pode ver o que pelo vinculo e da Task 1.6 (RNF06).
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import TokenInvalido, ler_token_acesso
from app.db.deps import DbSession
from app.models.usuario import Perfil, Usuario
from app.services import auth as servico

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
