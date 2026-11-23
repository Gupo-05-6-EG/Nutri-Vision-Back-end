"""cria tabela alimento_personalizado

Task 2.6 [Back] - Alimentos Personalizados (RF22).

Revision ID: 7d1e3b9a4c20
Revises: cb009bd17cf9
Create Date: 2026-10-13 17:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7d1e3b9a4c20"
down_revision: str | None = "cb009bd17cf9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alimento_personalizado",
        sa.Column("id", sa.Integer(), nullable=False),
        # A FK para a tabela de usuarios entra na Task 1.2, junto com o cadastro.
        sa.Column("paciente_id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=150), nullable=False),
        sa.Column("kcal_100g", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column("carbs_100g", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column("prot_100g", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column("gord_100g", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kcal_100g >= 0", name=op.f("ck_alimento_personalizado_kcal_nao_negativa")
        ),
        sa.CheckConstraint(
            "carbs_100g >= 0", name=op.f("ck_alimento_personalizado_carbs_nao_negativo")
        ),
        sa.CheckConstraint(
            "prot_100g >= 0", name=op.f("ck_alimento_personalizado_prot_nao_negativa")
        ),
        sa.CheckConstraint(
            "gord_100g >= 0", name=op.f("ck_alimento_personalizado_gord_nao_negativa")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alimento_personalizado")),
        sa.UniqueConstraint("paciente_id", "nome", name="uq_alimento_personalizado_paciente_nome"),
    )
    op.create_index(
        op.f("ix_alimento_personalizado_paciente_id"),
        "alimento_personalizado",
        ["paciente_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_alimento_personalizado_nome"),
        "alimento_personalizado",
        ["nome"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_alimento_personalizado_nome"), table_name="alimento_personalizado")
    op.drop_index(
        op.f("ix_alimento_personalizado_paciente_id"), table_name="alimento_personalizado"
    )
    op.drop_table("alimento_personalizado")
