"""Modelos do plano alimentar prescrito pelo nutricionista (RF09.1).

Um plano e uma lista de blocos de refeicao (cafe da manha, lanche da tarde,
ceia, ...), cada um com metas de kcal e proteinas e os alimentos indicados.

Cada paciente tem no maximo um plano ativo: prescrever um novo desativa o
anterior. O historico de versoes com auditoria fica para a Task 5.3 (RF08).
"""

from datetime import datetime, time
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Time,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PlanoAlimentar(Base):
    """Plano alimentar de um paciente, com seus blocos de refeicao."""

    __tablename__ = "planos_alimentares"
    __table_args__ = (Index("ix_planos_alimentares_paciente_ativo", "paciente_id", "ativo"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    paciente_id: Mapped[int] = mapped_column(
        ForeignKey("pacientes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # SET NULL: se a conta do nutricionista for removida, o paciente nao perde
    # o plano que ja recebeu.
    nutricionista_id: Mapped[int | None] = mapped_column(
        ForeignKey("nutricionistas.id", ondelete="SET NULL"), nullable=True
    )
    titulo: Mapped[str] = mapped_column(String(120), nullable=False)
    observacao: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    ativo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    refeicoes: Mapped[list["RefeicaoPlano"]] = relationship(
        back_populates="plano",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="RefeicaoPlano.ordem",
    )

    @property
    def totais(self) -> dict[str, Decimal]:
        """Metas do dia somadas a partir dos blocos (derivadas, nao colunas)."""
        return {
            "meta_kcal": sum((r.meta_kcal for r in self.refeicoes), Decimal("0")),
            "meta_proteinas_g": sum((r.meta_proteinas_g for r in self.refeicoes), Decimal("0")),
        }


class RefeicaoPlano(Base):
    """Um bloco de refeicao do plano, com as metas e os alimentos indicados."""

    __tablename__ = "refeicoes_plano"
    __table_args__ = (
        CheckConstraint("meta_kcal >= 0", name="meta_kcal_nao_negativa"),
        CheckConstraint("meta_proteinas_g >= 0", name="meta_proteinas_nao_negativa"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plano_id: Mapped[int] = mapped_column(
        ForeignKey("planos_alimentares.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Posicao do bloco no plano, na ordem em que o nutricionista montou.
    ordem: Mapped[int] = mapped_column(Integer, nullable=False)
    # Nome livre ("Lanche da tarde", "Ceia", ...): o plano nao se limita aos
    # quatro tipos de registro do RF19.
    nome: Mapped[str] = mapped_column(String(60), nullable=False)
    horario: Mapped[time | None] = mapped_column(Time, nullable=True)
    meta_kcal: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    meta_proteinas_g: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    observacao: Mapped[str | None] = mapped_column(String(500), nullable=True)

    plano: Mapped[PlanoAlimentar] = relationship(back_populates="refeicoes")
    alimentos: Mapped[list["AlimentoRefeicaoPlano"]] = relationship(
        back_populates="refeicao",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="AlimentoRefeicaoPlano.ordem",
    )


class AlimentoRefeicaoPlano(Base):
    """Um alimento indicado num bloco do plano, com a quantidade."""

    __tablename__ = "alimentos_refeicao_plano"
    __table_args__ = (CheckConstraint("quantidade_g > 0", name="quantidade_g_positiva"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    refeicao_plano_id: Mapped[int] = mapped_column(
        ForeignKey("refeicoes_plano.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ordem: Mapped[int] = mapped_column(Integer, nullable=False)
    nome_alimento: Mapped[str] = mapped_column(String(160), nullable=False)
    quantidade_g: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    # Opcional: o nutricionista pode escolher da TACO ou escrever livremente.
    alimento_taco_id: Mapped[int | None] = mapped_column(
        ForeignKey("alimento_taco.id", ondelete="SET NULL"), nullable=True
    )

    refeicao: Mapped[RefeicaoPlano] = relationship(back_populates="alimentos")
