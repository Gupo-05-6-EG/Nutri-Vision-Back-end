"""Modelo do Banco Nutricional TACO (RF02.2).

Escopo desta task: importar a Tabela Brasileira de Composicao de Alimentos
(TACO, 4a edicao, NEPA/UNICAMP) para o banco e expor busca por nome. Os
valores nutricionais sao por 100g, como na tabela original.

A FK de `alimento_id` em `itens_refeicao` (Task 2.1) entra depois, quando o
front passar a montar refeicoes a partir da busca desta task.
"""

from decimal import Decimal

from sqlalchemy import Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AlimentoTaco(Base):
    """Um alimento da tabela TACO, com os macros por 100g."""

    __tablename__ = "alimento_taco"

    id: Mapped[int] = mapped_column(primary_key=True)

    nome: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    categoria: Mapped[str] = mapped_column(String(80), nullable=False)

    kcal_100g: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    carbs_100g: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    prot_100g: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    gord_100g: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
