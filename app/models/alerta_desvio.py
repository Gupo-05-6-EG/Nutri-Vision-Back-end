"""Modelos de regras e alertas de desvio significativo de meta (Task 5.4, RF10.2).

- `RegraAlertaDesvio`: configuracao do nutricionista para o limiar de desvio
  calorico (ex.: > 20% acima ou abaixo da meta) e numero de dias consecutivos
  (ex.: 3 dias). Quando o nutricionista ainda nao salvou uma regra propria, o
  servico aplica o padrao de 20% por 3 dias consecutivos.
- `AlertaDesvioPlano`: alerta gerado pelo job diario quando o consumo do
  paciente desvia significativamente da meta (do plano ativo ou basal) por N
  dias seguidos, exibido no painel web e notificado ao nutricionista.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    false,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DirecaoDesvio(StrEnum):
    """Sentido predominante do desvio em relacao a meta diaria."""

    ACIMA = "acima"
    ABAIXO = "abaixo"
    AMBOS = "ambos"


class RegraAlertaDesvio(Base):
    """Regra configuravel por nutricionista para deteccao de desvio do plano."""

    __tablename__ = "regras_alerta_desvio"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nutricionista_id: Mapped[int] = mapped_column(
        ForeignKey("nutricionistas.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    percentual_desvio: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("20.00")
    )
    dias_consecutivos: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    ativo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class AlertaDesvioPlano(Base):
    """Alerta de desvio significativo entre consumo e meta diaria do paciente."""

    __tablename__ = "alertas_desvio_plano"
    __table_args__ = (
        UniqueConstraint(
            "nutricionista_id",
            "paciente_id",
            "data_referencia",
            name="uq_alertas_desvio_nutri_paciente_data",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nutricionista_id: Mapped[int] = mapped_column(
        ForeignKey("nutricionistas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    paciente_id: Mapped[int] = mapped_column(
        ForeignKey("pacientes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    data_referencia: Mapped[date] = mapped_column(Date, nullable=False)
    direcao: Mapped[str] = mapped_column(String(20), nullable=False)
    dias_consecutivos: Mapped[int] = mapped_column(Integer, nullable=False)
    percentual_limite: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    percentual_medio_desvio: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    meta_kcal: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    consumo_medio_kcal: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    lido: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    notificado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
