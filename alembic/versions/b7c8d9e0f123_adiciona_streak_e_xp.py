"""adiciona streak, XP e controle de processamento diario

Task 4.1 [Back] - Motor de Ofensiva (Streak) e XP (RF16).

Revision ID: b7c8d9e0f123
Revises: 9c2f8f2d7d1a
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7c8d9e0f123"
down_revision: str | None = "9c2f8f2d7d1a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # batch_alter_table para funcionar tambem no SQLite (que nao tem ADD CONSTRAINT).
    with op.batch_alter_table("pacientes") as batch_op:
        batch_op.add_column(sa.Column("streak", sa.Integer(), server_default="0", nullable=False))
        batch_op.add_column(sa.Column("xp", sa.Integer(), server_default="0", nullable=False))
        batch_op.add_column(sa.Column("gamificacao_processada_em", sa.Date(), nullable=True))
        # op.f(): o nome ja segue a naming convention e nao deve ser prefixado de novo.
        batch_op.create_check_constraint(op.f("ck_pacientes_streak_nao_negativa"), "streak >= 0")
        batch_op.create_check_constraint(op.f("ck_pacientes_xp_nao_negativo"), "xp >= 0")


def downgrade() -> None:
    with op.batch_alter_table("pacientes") as batch_op:
        batch_op.drop_constraint(op.f("ck_pacientes_xp_nao_negativo"), type_="check")
        batch_op.drop_constraint(op.f("ck_pacientes_streak_nao_negativa"), type_="check")
        batch_op.drop_column("gamificacao_processada_em")
        batch_op.drop_column("xp")
        batch_op.drop_column("streak")
