"""cria tabela de pacientes

Task 1.3 [Back] - Calculo Basal (RF14).

Revision ID: e4cfca49122c
Revises: 50fb3bbd67e6
Create Date: 2026-09-21 14:48:16.100078

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e4cfca49122c"
down_revision: str | None = "50fb3bbd67e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pacientes",
        # Sem autoincrement e sem FK: o id e o do usuario, e a tabela de usuarios
        # nasce na Task 1.2, que adiciona a constraint.
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("peso_kg", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("altura_cm", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("idade", sa.Integer(), nullable=True),
        sa.Column("genero", sa.String(length=30), nullable=True),
        sa.Column("nivel_atividade", sa.String(length=30), nullable=True),
        sa.Column("meta_kcal", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("origem_meta", sa.String(length=30), nullable=True),
        sa.CheckConstraint("altura_cm > 0", name=op.f("ck_pacientes_altura_cm_positiva")),
        sa.CheckConstraint("idade > 0", name=op.f("ck_pacientes_idade_positiva")),
        sa.CheckConstraint("meta_kcal >= 0", name=op.f("ck_pacientes_meta_kcal_nao_negativa")),
        sa.CheckConstraint("peso_kg > 0", name=op.f("ck_pacientes_peso_kg_positivo")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pacientes")),
    )


def downgrade() -> None:
    op.drop_table("pacientes")
