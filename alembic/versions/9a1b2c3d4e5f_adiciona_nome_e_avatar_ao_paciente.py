"""adiciona nome e avatar ao paciente

Modulo: Privacidade e Conformidade (LGPD) - Item 51 (RF29).

Revision ID: 9a1b2c3d4e5f
Revises: 8f2c3d1e9a4b
Create Date: 2026-10-26 21:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9a1b2c3d4e5f"
down_revision: str | None = "8f2c3d1e9a4b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("pacientes", sa.Column("nome", sa.String(length=100), nullable=True))
    op.add_column("pacientes", sa.Column("avatar", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("pacientes", "avatar")
    op.drop_column("pacientes", "nome")
