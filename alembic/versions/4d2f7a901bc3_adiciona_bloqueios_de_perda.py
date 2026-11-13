"""Adiciona o saldo de bloqueios de perda da ofensiva (RF17)."""

import sqlalchemy as sa
from alembic import op

revision = "4d2f7a901bc3"
down_revision = "c4d9e1f6a2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pacientes",
        sa.Column("bloqueios_perda", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        op.f("ck_pacientes_bloqueios_nao_negativos"), "pacientes", "bloqueios_perda >= 0"
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_pacientes_bloqueios_nao_negativos"), "pacientes", type_="check"
    )
    op.drop_column("pacientes", "bloqueios_perda")
