"""Modelos dos lembretes de refeicao (Task 2.8, RF26).

- `LembreteRefeicao`: horario configurado pelo paciente para cada tipo de
  refeicao (cafe, almoco, lanche, jantar). Um por (paciente, tipo).
- `DispositivoPush`: token FCM de cada aparelho do paciente. E o endereco para
  onde o job envia o push; sem ele nao ha como notificar.
"""

from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Time,
    UniqueConstraint,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LembreteRefeicao(Base):
    """Horario de lembrete de um tipo de refeicao de um paciente."""

    __tablename__ = "lembretes_refeicao"
    __table_args__ = (
        UniqueConstraint("paciente_id", "tipo", name="uq_lembretes_refeicao_paciente_tipo"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    paciente_id: Mapped[int] = mapped_column(
        ForeignKey("pacientes.id", ondelete="CASCADE"), nullable=False
    )

    # Valor de `TipoRefeicao` (cafe_da_manha, almoco, lanche, jantar).
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)

    # Hora local (America/Sao_Paulo) em que o lembrete deve disparar.
    horario: Mapped[time] = mapped_column(Time, nullable=False)

    ativo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )

    # Ultimo dia (local) em que o push foi enviado: garante no maximo um
    # lembrete por refeicao por dia, mesmo que o job rode varias vezes.
    ultimo_envio_em: Mapped[date | None] = mapped_column(Date, nullable=True)

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class DispositivoPush(Base):
    """Token FCM de um aparelho do paciente."""

    __tablename__ = "dispositivos_push"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    paciente_id: Mapped[int] = mapped_column(
        ForeignKey("pacientes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
