"""Modelos de vinculo entre paciente e nutricionista (Task 1.4)."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StatusCodigoVinculacao(StrEnum):
    ATIVO = "ativo"
    RESGATADO = "resgatado"
    EXPIRADO = "expirado"


class CodigoVinculacao(Base):
    """Codigo temporario gerado por nutricionista para permitir o primeiro vinculo."""

    __tablename__ = "codigo_vinculacao"
    __table_args__ = (
        Index("ix_codigo_vinculacao_nutricionista_status", "nutricionista_id", "status"),
        UniqueConstraint("codigo_hash", name="uq_codigo_vinculacao_codigo_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nutricionista_id: Mapped[int] = mapped_column(
        ForeignKey("nutricionistas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    nutricionista_nome: Mapped[str] = mapped_column(String(160), nullable=False)
    nutricionista_foto_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    codigo_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=StatusCodigoVinculacao.ATIVO.value,
    )
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resgatado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paciente_id: Mapped[int | None] = mapped_column(
        ForeignKey("pacientes.id", ondelete="SET NULL"),
        nullable=True,
    )


class Vinculo(Base):
    """Relacionamento persistido entre paciente e nutricionista."""

    __tablename__ = "vinculos"
    __table_args__ = (
        UniqueConstraint(
            "nutricionista_id",
            "paciente_id",
            name="uq_vinculos_nutricionista_paciente",
        ),
        CheckConstraint(
            "nutricionista_id <> paciente_id",
            name="nutricionista_diferente_do_paciente",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nutricionista_id: Mapped[int] = mapped_column(
        ForeignKey("nutricionistas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    paciente_id: Mapped[int] = mapped_column(
        ForeignKey("pacientes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
