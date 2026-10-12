"""Modelos de Usuario e Nutricionista (RF13).

Os perfis do sistema moram em `usuarios`; os dados especificos de cada perfil
ficam em tabelas proprias com o mesmo id.
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
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True)
    senha_hash: Mapped[str] = mapped_column(String(60), nullable=False)
    perfil: Mapped[str] = mapped_column(String(20), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Nutricionista(Base):
    __tablename__ = "nutricionistas"

    id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), primary_key=True, autoincrement=False
    )
    crn: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
