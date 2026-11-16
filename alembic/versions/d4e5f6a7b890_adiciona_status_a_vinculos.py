"""adiciona status aos vinculos

Task 1.5 [Back] - Status e Endpoints de Vinculo (RF14, RF15).

Revision ID: d4e5f6a7b890
Revises: 8f2c3d1e9a4b
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d4e5f6a7b890"
down_revision: str | None = "8f2c3d1e9a4b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "vinculos",
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="ativo",
        ),
    )
    op.alter_column(
        "vinculos",
        "status",
        existing_type=sa.String(length=20),
        server_default="pendente",
    )


def downgrade() -> None:
    op.drop_column("vinculos", "status")
