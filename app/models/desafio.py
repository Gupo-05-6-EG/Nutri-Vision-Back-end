"""Modelos de desafios sociais entre pacientes (RF05.2, RF05.3)."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TipoDesafio(StrEnum):
    REFEICOES = "refeicoes"
    VARIACAO_CALORICA = "variacao_calorica"
    SEQUENCIA_META = "sequencia_meta"


class StatusParticipante(StrEnum):
    CONVIDADO = "convidado"
    ACEITO = "aceito"
    RECUSADO = "recusado"


class Desafio(Base):
    __tablename__ = "desafios"
    __table_args__ = (
        CheckConstraint("fim_em > inicio_em", name="datas_validas"),
        CheckConstraint("criador_id > 0", name="criador_positivo"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    criador_id: Mapped[int] = mapped_column(
        ForeignKey("pacientes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    regra: Mapped[str] = mapped_column(String(500), nullable=False)
    inicio_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fim_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ParticipanteDesafio(Base):
    __tablename__ = "participantes_desafio"
    __table_args__ = (UniqueConstraint("desafio_id", "paciente_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    desafio_id: Mapped[int] = mapped_column(
        ForeignKey("desafios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    paciente_id: Mapped[int] = mapped_column(
        ForeignKey("pacientes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=StatusParticipante.CONVIDADO.value,
        server_default=StatusParticipante.CONVIDADO.value,
    )
    convidado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    respondido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
