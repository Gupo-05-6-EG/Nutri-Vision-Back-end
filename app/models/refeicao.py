"""Modelos de Refeicao e ItemRefeicao (RF04, RF12, RF19).

Escopo desta task: a estrutura do registro de consumo. Campos que pertencem a
outras tasks entram por migration depois:

- estimativa da IA vs valor confirmado no item -> Task 2.7 (RF23)
- `alimento_id` apontando para a tabela TACO -> Task 2.2 (RF02.2)
"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

CAMPOS_NUTRICIONAIS = ("calorias_kcal", "proteinas_g", "carboidratos_g", "gorduras_g")


class TipoRefeicao(StrEnum):
    """Categoria da refeicao (RF19), usada para organizar e filtrar o historico."""

    CAFE_DA_MANHA = "cafe_da_manha"
    ALMOCO = "almoco"
    LANCHE = "lanche"
    JANTAR = "jantar"


def somar(itens: "list[ItemRefeicao]", campo: str) -> Decimal:
    """Soma um campo nutricional de uma lista de itens."""
    return sum((getattr(item, campo) for item in itens), Decimal("0"))


class Refeicao(Base):
    """Uma refeicao registrada por um paciente, com seus itens."""

    __tablename__ = "refeicoes"
    __table_args__ = (
        Index("ix_refeicoes_paciente_consumida_em", "paciente_id", "consumida_em"),
        Index("ix_refeicoes_paciente_tipo", "paciente_id", "tipo"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    paciente_id: Mapped[int] = mapped_column(
        ForeignKey("pacientes.id", ondelete="CASCADE"), nullable=False, index=True
    )

    consumida_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Cafe da manha, almoco, lanche ou jantar (RF19). Quando nao informado na
    # criacao, o service sugere automaticamente pelo horario de `consumida_em`
    # (ver `sugerir_tipo` em app/services/refeicoes.py).
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)

    observacao: Mapped[str | None] = mapped_column(String(500), nullable=True)

    criada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    atualizada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    itens: Mapped[list["ItemRefeicao"]] = relationship(
        back_populates="refeicao",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ItemRefeicao.id",
    )

    @property
    def totais(self) -> dict[str, Decimal]:
        """Calorias e macros somados a partir dos itens (RF12).

        Os totais sao derivados, nao colunas: guardar a soma no banco abriria a
        porta para ela divergir dos itens depois de uma edicao.
        """
        return {campo: somar(self.itens, campo) for campo in CAMPOS_NUTRICIONAIS}


class ItemRefeicao(Base):
    """Um alimento dentro de uma refeicao, com a quantidade e os macros."""

    __tablename__ = "itens_refeicao"
    __table_args__ = (
        CheckConstraint("quantidade_g > 0", name="quantidade_g_positiva"),
        CheckConstraint("calorias_kcal >= 0", name="calorias_nao_negativas"),
        CheckConstraint("proteinas_g >= 0", name="proteinas_nao_negativas"),
        CheckConstraint("carboidratos_g >= 0", name="carboidratos_nao_negativos"),
        CheckConstraint("gorduras_g >= 0", name="gorduras_nao_negativas"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    refeicao_id: Mapped[int] = mapped_column(
        ForeignKey("refeicoes.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Texto livre por enquanto; a Task 2.2 traz a TACO e o alimento_id.
    nome_alimento: Mapped[str] = mapped_column(String(160), nullable=False)

    quantidade_g: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    calorias_kcal: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    proteinas_g: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    carboidratos_g: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    gorduras_g: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)

    refeicao: Mapped[Refeicao] = relationship(back_populates="itens")
