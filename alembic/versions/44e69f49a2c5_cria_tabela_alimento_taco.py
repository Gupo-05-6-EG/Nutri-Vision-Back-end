"""cria tabela alimento_taco

Task 2.2 [Back] - Banco Nutricional TACO (RF02.2).

Revision ID: 44e69f49a2c5
Revises: e4cfca49122c
Create Date: 2026-09-21 15:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "44e69f49a2c5"
down_revision: str | None = "e4cfca49122c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alimento_taco",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=150), nullable=False),
        sa.Column("categoria", sa.String(length=80), nullable=False),
        sa.Column("kcal_100g", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column("carbs_100g", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column("prot_100g", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column("gord_100g", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alimento_taco")),
    )
    op.create_index(
        op.f("ix_alimento_taco_nome"),
        "alimento_taco",
        ["nome"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_alimento_taco_nome"), table_name="alimento_taco")
    op.drop_table("alimento_taco")
