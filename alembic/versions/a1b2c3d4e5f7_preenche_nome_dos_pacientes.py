"""preenche o nome social dos pacientes a partir do usuario

O cadastro criava o paciente sem nome: ranking, amigos e placar ficavam sem
nome. O cadastro passa a copiar `usuarios.nome`; aqui o backfill dos que ja
existem.

Revision ID: a1b2c3d4e5f7
Revises: f1a2b3c4d5e6
Create Date: 2026-11-19
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a1b2c3d4e5f7"
down_revision: str | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE pacientes SET nome = "
        "(SELECT substr(usuarios.nome, 1, 100) FROM usuarios WHERE usuarios.id = pacientes.id) "
        "WHERE nome IS NULL"
    )


def downgrade() -> None:
    # Dado preenchido: nao ha como saber quais estavam vazios antes.
    pass
