"""adiciona streak, XP e controle de processamento diario

Revision ID: b7c8d9e0f123
Revises: a1b2c3d4e5f6
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7c8d9e0f123"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "pacientes", sa.Column("streak", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column("pacientes", sa.Column("xp", sa.Integer(), server_default="0", nullable=False))
    op.add_column("pacientes", sa.Column("gamificacao_processada_em", sa.Date(), nullable=True))
    op.create_check_constraint("ck_pacientes_streak_nao_negativa", "pacientes", "streak >= 0")
    op.create_check_constraint("ck_pacientes_xp_nao_negativo", "pacientes", "xp >= 0")


def downgrade() -> None:
    op.drop_constraint("ck_pacientes_xp_nao_negativo", "pacientes", type_="check")
    op.drop_constraint("ck_pacientes_streak_nao_negativa", "pacientes", type_="check")
    op.drop_column("pacientes", "gamificacao_processada_em")
    op.drop_column("pacientes", "xp")
    op.drop_column("pacientes", "streak")
