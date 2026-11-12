"""Resgate de ofensiva e conquistas (Tasks 4.2 e 4.6)."""

import sqlalchemy as sa
from alembic import op

revision = "bb23cc45dd67"
down_revision = "aa12bb34cc56"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "pacientes", sa.Column("bloqueios_perda", sa.Integer(), nullable=False, server_default="0")
    )
    op.create_check_constraint(
        "ck_pacientes_bloqueios_nao_negativos", "pacientes", "bloqueios_perda >= 0"
    )
    op.create_table(
        "conquistas_paciente",
        sa.Column(
            "paciente_id",
            sa.Integer(),
            sa.ForeignKey("pacientes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("codigo", sa.String(40), primary_key=True),
        sa.Column(
            "obtida_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade():
    op.drop_table("conquistas_paciente")
    op.drop_constraint("ck_pacientes_bloqueios_nao_negativos", "pacientes", type_="check")
    op.drop_column("pacientes", "bloqueios_perda")
