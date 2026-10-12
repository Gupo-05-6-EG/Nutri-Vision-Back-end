"""Utilidades de autenticacao JWT usadas pelos endpoints do sistema."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, ValidationError

from app.core.config import get_settings
from app.models.usuario import Perfil

# Alias para compatibilidade com o codigo existente da Task 1.4
PerfilUsuario = Perfil

bearer_scheme = HTTPBearer(auto_error=False)

NAO_AUTENTICADO = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Nao autenticado",
    headers={"WWW-Authenticate": "Bearer"},
)

TOKEN_INVALIDO = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Token invalido",
    headers={"WWW-Authenticate": "Bearer"},
)


class TokenInvalido(Exception):
    """Token ausente, malformado, com assinatura invalida ou expirado."""


class UsuarioAutenticado(BaseModel):
    id: int = Field(gt=0)
    perfil: Perfil
    nome: str
    foto_url: str | None = None


def criar_token_acesso(
    usuario_id: int,
    perfil: str,
    nome: str | None = None,
    foto_url: str | None = None,
    expires_delta: timedelta | None = None,
) -> tuple[str, datetime]:
    """Gera o JWT de acesso padrao (compativel com Task 1.2).

    Devolve a string do token e o datetime UTC em que ele expira.
    """
    settings = get_settings()
    agora = datetime.now(UTC)
    minutos = expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    expira_em = agora + minutos
    payload: dict[str, Any] = {
        "sub": str(usuario_id),
        "perfil": str(perfil),
        "iat": agora,
        "exp": expira_em,
    }
    if nome is not None:
        payload["nome"] = nome
    if foto_url is not None:
        payload["foto_url"] = foto_url
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return token, expira_em


def create_access_token(
    subject: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """Cria um JWT assinado compativel com dicionarios subject."""
    settings = get_settings()
    payload = subject.copy()
    if "sub" in payload:
        payload["sub"] = str(payload["sub"])
    agora = datetime.now(UTC)
    minutos = expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload["exp"] = agora + minutos
    if "iat" not in payload:
        payload["iat"] = agora
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def ler_token_acesso(token: str) -> dict[str, Any]:
    """Valida o JWT e devolve o payload decodificado e validado."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"require": ["sub", "exp"]},
        )
    except jwt.PyJWTError as erro:
        raise TokenInvalido("Token invalido ou expirado") from erro

    sub = payload.get("sub")
    if sub is None:
        raise TokenInvalido("Claim sub ausente")

    try:
        usuario_id = int(sub)
        if usuario_id <= 0:
            raise ValueError("sub deve ser positivo")
    except (ValueError, TypeError) as erro:
        raise TokenInvalido("sub com valor nao numerico") from erro

    perfil = payload.get("perfil")
    if not perfil:
        raise TokenInvalido("Claim perfil ausente")

    try:
        Perfil(str(perfil))
    except ValueError as erro:
        raise TokenInvalido(f"Perfil desconhecido: {perfil}") from erro

    return payload


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> UsuarioAutenticado:
    """Decodifica e valida o JWT, garantindo perfil e campos obrigatorios."""
    if credentials is None:
        raise NAO_AUTENTICADO

    try:
        payload = ler_token_acesso(credentials.credentials)
        usuario_id = int(payload["sub"])
        perfil = Perfil(str(payload["perfil"]))
    except (TokenInvalido, ValueError):
        raise TOKEN_INVALIDO from None

    nome = payload.get("nome") or f"Usuario {usuario_id}"
    foto_url = payload.get("foto_url")

    try:
        return UsuarioAutenticado(
            id=usuario_id,
            perfil=perfil,
            nome=nome,
            foto_url=foto_url,
        )
    except ValidationError:
        raise TOKEN_INVALIDO from None


def require_perfil(perfil: Perfil):
    """Cria uma dependencia que garante o perfil do usuario autenticado."""

    def _dependency(
        usuario: Annotated[UsuarioAutenticado, Depends(get_current_user)],
    ) -> UsuarioAutenticado:
        if usuario.perfil != perfil:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Perfil nao autorizado",
            )
        return usuario

    return _dependency