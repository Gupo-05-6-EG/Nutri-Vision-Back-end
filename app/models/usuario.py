"""Modelos de Usuario e Nutricionista (RF13).

Todo mundo que entra no sistema e um `Usuario` (credenciais + perfil). Os dados
especificos de cada perfil ficam numa tabela propria, com o mesmo id:

- paciente     -> `pacientes` (triagem e teto calorico, Task 1.3)
- nutricionista -> `nutricionistas` (CRN)

A senha nunca e gravada: so o hash bcrypt (`core/security.py`).
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Perfil(StrEnum):
    PACIENTE = "paciente"
    NUTRICIONISTA = "nutricionista"


class Usuario(Base):
    """Credenciais e perfil de quem acessa o app ou o painel."""

    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)

    # Sempre gravado em minusculas (o schema normaliza), entao o unique basta
    # para impedir duplicatas que so diferem na caixa.
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True)
    senha_hash: Mapped[str] = mapped_column(String(60), nullable=False)
    perfil: Mapped[str] = mapped_column(String(20), nullable=False)

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Nutricionista(Base):
    """Dados especificos do nutricionista. O id e o do usuario."""

    __tablename__ = "nutricionistas"

    id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), primary_key=True, autoincrement=False
    )
    # Registro no Conselho Regional de Nutricionistas, ex.: "CRN-3 12345".
    crn: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
