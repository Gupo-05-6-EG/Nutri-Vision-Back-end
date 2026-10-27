"""Modelo de Amizades (RF05).

Rede de relacionamentos sociais entre pacientes para competicoes, desafios e
ranking semanal (Leaderboard).
"""

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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class StatusAmizade(StrEnum):
    """Estado do convite de amizade."""

    PENDENTE = "pendente"
    ACEITO = "aceito"
    RECUSADO = "recusado"


class Amizade(Base):
    """Relacionamento de amizade entre dois pacientes."""

    __tablename__ = "amizades"
    __table_args__ = (
        CheckConstraint("pac_id != amigo_id", name="nao_auto_amizade"),
        UniqueConstraint("pac_id", "amigo_id", name="uq_amizades_pac_amigo"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pac_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pacientes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amigo_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pacientes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=StatusAmizade.PENDENTE,
        server_default=StatusAmizade.PENDENTE,
    )
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    paciente = relationship("Paciente", foreign_keys=[pac_id])
    amigo = relationship("Paciente", foreign_keys=[amigo_id])
