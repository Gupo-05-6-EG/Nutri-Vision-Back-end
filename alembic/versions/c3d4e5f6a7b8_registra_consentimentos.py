"""registra aceite e revogacao de consentimentos LGPD

Task 6.1 [Back] - Consentimento e Direitos do Titular (RF28, RNF07).

Revision ID: c3d4e5f6a7b8
Revises: d4e5f6a7b890
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "d4e5f6a7b890"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "consentimentos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("versao_termo", sa.String(length=40), nullable=False),
        sa.Column("aceito_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("revogado_em", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["usuarios.id"], name=op.f("fk_consentimentos_usuario_id_usuarios"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_consentimentos")),
    )
    op.create_index(
        op.f("ix_consentimentos_usuario_id"), "consentimentos", ["usuario_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_consentimentos_usuario_id"), table_name="consentimentos")
    op.drop_table("consentimentos")
