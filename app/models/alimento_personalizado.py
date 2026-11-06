"""Modelo de Alimento Personalizado (RF22).

Alimento cadastrado pelo paciente quando nao existe correspondencia na TACO.
Os valores sao por 100g, como na tabela `alimento_taco`, para que os dois
possam ser buscados e calculados do mesmo jeito.

`paciente_id` fica sem FK por enquanto, igual a `refeicoes`: a tabela de
usuarios nasce na Task 1.2, que adiciona a constraint por migration. Por isso,
cada alimento so aparece na busca do paciente que o cadastrou.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AlimentoPersonalizado(Base):
    """Um alimento criado por um paciente, com os macros por 100g."""

    __tablename__ = "alimento_personalizado"
    __table_args__ = (
        UniqueConstraint("paciente_id", "nome", name="uq_alimento_personalizado_paciente_nome"),
        CheckConstraint("kcal_100g >= 0", name="kcal_nao_negativa"),
        CheckConstraint("carbs_100g >= 0", name="carbs_nao_negativo"),
        CheckConstraint("prot_100g >= 0", name="prot_nao_negativa"),
        CheckConstraint("gord_100g >= 0", name="gord_nao_negativa"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    paciente_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    nome: Mapped[str] = mapped_column(String(150), nullable=False, index=True)

    kcal_100g: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    carbs_100g: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    prot_100g: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    gord_100g: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
