"""adiciona coluna tipo em refeicoes

Task 2.4 [Back] - Categorizacao de Refeicoes (RF19).

Linhas existentes (se houver) sao preenchidas com "lanche" no upgrade; o
service passa a decidir o tipo (informado pelo cliente ou sugerido pelo
horario) a partir daqui, entao o valor por omissao do banco e so uma rede de
seguranca para backfill e pode ser removido depois.

Revision ID: cb009bd17cf9
Revises: 44e69f49a2c5
Create Date: 2026-09-28 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "cb009bd17cf9"
down_revision: str | None = "44e69f49a2c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "refeicoes",
        sa.Column("tipo", sa.String(length=20), nullable=False, server_default="lanche"),
    )
    with op.batch_alter_table("refeicoes") as batch_op:
        batch_op.alter_column("tipo", server_default=None)
    op.create_index(
        "ix_refeicoes_paciente_tipo",
        "refeicoes",
        ["paciente_id", "tipo"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_refeicoes_paciente_tipo", table_name="refeicoes")
    op.drop_column("refeicoes", "tipo")
