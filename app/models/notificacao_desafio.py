"""Modelo de controle de notificacoes motivacionais de desafios (Task 4.5, RF05.5).

Garante o limite de frequencia (no maximo um push motivacional de desafio por
participante por dia local), alem de registrar a posicao e os dias restantes
informados no momento do envio.
"""

from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NotificacaoDesafio(Base):
    """Registro de envio diario de push motivacional de desafio para um paciente."""

    __tablename__ = "notificacoes_desafio"
    __table_args__ = (
        UniqueConstraint(
            "paciente_id",
            "enviado_em",
            name="uq_notificacoes_desafio_paciente_dia",
        ),
        CheckConstraint("posicao >= 1", name="posicao_positiva"),
        CheckConstraint("dias_restantes >= 0", name="dias_restantes_nao_negativos"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    paciente_id: Mapped[int] = mapped_column(
        ForeignKey("pacientes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    desafio_id: Mapped[int] = mapped_column(
        ForeignKey("desafios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    posicao: Mapped[int] = mapped_column(Integer, nullable=False)
    dias_restantes: Mapped[int] = mapped_column(Integer, nullable=False)
    enviado_em: Mapped[date] = mapped_column(Date, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

