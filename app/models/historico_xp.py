"""Modelo de Historico de XP (RF05, RF16).

Registra eventos individuais de ganho de experiencia para permitir o calculo
dinamico do ranking na janela semanal vigente e auditoria de gamificacao.
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class HistoricoXP(Base):
    """Evento individual de ganho de experiencia (XP) por um paciente."""

    __tablename__ = "historico_xp"
    __table_args__ = (CheckConstraint("quantidade > 0", name="quantidade_positiva"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    paciente_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pacientes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quantidade: Mapped[int] = mapped_column(Integer, nullable=False)
    motivo: Mapped[str] = mapped_column(String(100), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    paciente = relationship("Paciente", foreign_keys=[paciente_id])
