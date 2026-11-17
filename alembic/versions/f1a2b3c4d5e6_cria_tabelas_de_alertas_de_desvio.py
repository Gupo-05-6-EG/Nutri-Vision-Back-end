"""cria tabelas de regras e alertas de desvio de meta

Task 5.4 [Back] - Alertas de Desvio de Meta (RF10.2).

Revision ID: f1a2b3c4d5e6
Revises: 6e7f8a9b0c1d
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "6e7f8a9b0c1d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "regras_alerta_desvio",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nutricionista_id", sa.Integer(), nullable=False),
        sa.Column("percentual_desvio", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("dias_consecutivos", sa.Integer(), nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["nutricionista_id"],
            ["nutricionistas.id"],
            name=op.f("fk_regras_alerta_desvio_nutricionista_id_nutricionistas"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_regras_alerta_desvio")),
        sa.UniqueConstraint(
            "nutricionista_id", name=op.f("uq_regras_alerta_desvio_nutricionista_id")
        ),
    )

    op.create_table(
        "alertas_desvio_plano",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nutricionista_id", sa.Integer(), nullable=False),
        sa.Column("paciente_id", sa.Integer(), nullable=False),
        sa.Column("data_referencia", sa.Date(), nullable=False),
        sa.Column("direcao", sa.String(length=20), nullable=False),
        sa.Column("dias_consecutivos", sa.Integer(), nullable=False),
        sa.Column("percentual_limite", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("percentual_medio_desvio", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column("meta_kcal", sa.Numeric(precision=7, scale=2), nullable=False),
        sa.Column("consumo_medio_kcal", sa.Numeric(precision=7, scale=2), nullable=False),
        sa.Column("lido", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("notificado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["nutricionista_id"],
            ["nutricionistas.id"],
            name=op.f("fk_alertas_desvio_plano_nutricionista_id_nutricionistas"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["pacientes.id"],
            name=op.f("fk_alertas_desvio_plano_paciente_id_pacientes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alertas_desvio_plano")),
        sa.UniqueConstraint(
            "nutricionista_id",
            "paciente_id",
            "data_referencia",
            name="uq_alertas_desvio_nutri_paciente_data",
        ),
    )
    op.create_index(
        op.f("ix_alertas_desvio_plano_nutricionista_id"),
        "alertas_desvio_plano",
        ["nutricionista_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_alertas_desvio_plano_paciente_id"),
        "alertas_desvio_plano",
        ["paciente_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_alertas_desvio_plano_paciente_id"), table_name="alertas_desvio_plano"
    )
    op.drop_index(
        op.f("ix_alertas_desvio_plano_nutricionista_id"), table_name="alertas_desvio_plano"
    )
    op.drop_table("alertas_desvio_plano")
    op.drop_table("regras_alerta_desvio")

