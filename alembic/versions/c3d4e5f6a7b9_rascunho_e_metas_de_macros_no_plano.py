"""rascunho de plano e metas de carboidrato e gordura por refeicao

Revision ID: c3d4e5f6a7b9
Revises: b2c3d4e5f6a8
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b9"
down_revision: str | None = "b2c3d4e5f6a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "planos_alimentares",
        sa.Column("rascunho", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "refeicoes_plano",
        sa.Column("meta_carboidratos_g", sa.Numeric(precision=6, scale=2), nullable=True),
    )
    op.add_column(
        "refeicoes_plano",
        sa.Column("meta_gorduras_g", sa.Numeric(precision=6, scale=2), nullable=True),
    )


def downgrade() -> None:
    with op.batch_alter_table("refeicoes_plano") as batch:
        batch.drop_column("meta_gorduras_g")
        batch.drop_column("meta_carboidratos_g")
    op.execute("DELETE FROM planos_alimentares WHERE rascunho")
    with op.batch_alter_table("planos_alimentares") as batch:
        batch.drop_column("rascunho")
