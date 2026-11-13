"""Cria o registro de conquistas dos pacientes (RF05.6)."""

import sqlalchemy as sa
from alembic import op

revision = "7c46f031ab29"
down_revision = "c4d9e1f6a2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conquistas_paciente",
        sa.Column("paciente_id", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.String(40), nullable=False),
        sa.Column("obtida_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["paciente_id"], ["pacientes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("paciente_id", "codigo"),
    )


def downgrade() -> None:
    op.drop_table("conquistas_paciente")
