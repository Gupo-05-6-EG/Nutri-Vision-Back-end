"""Utilidades de autenticacao JWT usadas pelos endpoints de vinculo."""

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app.core.config import get_settings

bearer_scheme = HTTPBearer(auto_error=False)


class PerfilUsuario(StrEnum):
    NUTRICIONISTA = "nutricionista"
    PACIENTE = "paciente"


class UsuarioAutenticado(BaseModel):
    id: int = Field(gt=0)
    perfil: PerfilUsuario
    nome: str
    foto_url: str | None = None


def create_access_token(subject: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """Cria um JWT assinado com os dados informados."""
    settings = get_settings()
    payload = subject.copy()
    if "sub" in payload:
        payload["sub"] = str(payload["sub"])
    expiracao = datetime.now(UTC) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    payload["exp"] = expiracao
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> UsuarioAutenticado:
    """Decodifica o JWT do header Authorization e normaliza o usuario autenticado."""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nao autenticado")

    settings = get_settings()
    try:
        payload = jwt.decode(credentials.credentials, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        usuario_id = payload.get("sub")
        perfil = payload.get("perfil")
        nome = payload.get("nome")
        foto_url = payload.get("foto_url")
    except jwt.PyJWTError as exc:  # pragma: no cover - dependente da biblioteca
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalido") from exc

    if usuario_id is None or perfil is None or nome is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalido")

    return UsuarioAutenticado(id=int(usuario_id), perfil=PerfilUsuario(perfil), nome=nome, foto_url=foto_url)


def require_perfil(perfil: PerfilUsuario):
    """Cria uma dependencia que garante o perfil do usuario autenticado."""

    def _dependency(usuario: UsuarioAutenticado = Depends(get_current_user)) -> UsuarioAutenticado:
        if usuario.perfil != perfil:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Perfil nao autorizado")
        return usuario

    return _dependency