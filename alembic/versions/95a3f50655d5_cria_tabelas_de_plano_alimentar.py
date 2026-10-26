"""cria tabelas de plano alimentar

Task 5.1 - Construtor de Planos Alimentares (RF09.1).

Revision ID: 95a3f50655d5
Revises: b7c8d9e0f123
Create Date: 2026-10-26 19:57:45.774022

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "95a3f50655d5"
down_revision: str | None = "b7c8d9e0f123"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "planos_alimentares",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("paciente_id", sa.Integer(), nullable=False),
        sa.Column("nutricionista_id", sa.Integer(), nullable=True),
        sa.Column("titulo", sa.String(length=120), nullable=False),
        sa.Column("observacao", sa.String(length=1000), nullable=True),
        sa.Column("ativo", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["nutricionista_id"],
            ["nutricionistas.id"],
            name=op.f("fk_planos_alimentares_nutricionista_id_nutricionistas"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["pacientes.id"],
            name=op.f("fk_planos_alimentares_paciente_id_pacientes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_planos_alimentares")),
    )
    op.create_index(
        "ix_planos_alimentares_paciente_ativo",
        "planos_alimentares",
        ["paciente_id", "ativo"],
        unique=False,
    )
    op.create_index(
        op.f("ix_planos_alimentares_paciente_id"),
        "planos_alimentares",
        ["paciente_id"],
        unique=False,
    )

    op.create_table(
        "refeicoes_plano",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plano_id", sa.Integer(), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=60), nullable=False),
        sa.Column("horario", sa.Time(), nullable=True),
        sa.Column("meta_kcal", sa.Numeric(precision=7, scale=2), nullable=False),
        sa.Column("meta_proteinas_g", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column("observacao", sa.String(length=500), nullable=True),
        sa.CheckConstraint(
            "meta_kcal >= 0", name=op.f("ck_refeicoes_plano_meta_kcal_nao_negativa")
        ),
        sa.CheckConstraint(
            "meta_proteinas_g >= 0",
            name=op.f("ck_refeicoes_plano_meta_proteinas_nao_negativa"),
        ),
        sa.ForeignKeyConstraint(
            ["plano_id"],
            ["planos_alimentares.id"],
            name=op.f("fk_refeicoes_plano_plano_id_planos_alimentares"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refeicoes_plano")),
    )
    op.create_index(
        op.f("ix_refeicoes_plano_plano_id"), "refeicoes_plano", ["plano_id"], unique=False
    )

    op.create_table(
        "alimentos_refeicao_plano",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("refeicao_plano_id", sa.Integer(), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("nome_alimento", sa.String(length=160), nullable=False),
        sa.Column("quantidade_g", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("alimento_taco_id", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "quantidade_g > 0",
            name=op.f("ck_alimentos_refeicao_plano_quantidade_g_positiva"),
        ),
        sa.ForeignKeyConstraint(
            ["alimento_taco_id"],
            ["alimento_taco.id"],
            name=op.f("fk_alimentos_refeicao_plano_alimento_taco_id_alimento_taco"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["refeicao_plano_id"],
            ["refeicoes_plano.id"],
            name=op.f("fk_alimentos_refeicao_plano_refeicao_plano_id_refeicoes_plano"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alimentos_refeicao_plano")),
    )
    op.create_index(
        op.f("ix_alimentos_refeicao_plano_refeicao_plano_id"),
        "alimentos_refeicao_plano",
        ["refeicao_plano_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_alimentos_refeicao_plano_refeicao_plano_id"),
        table_name="alimentos_refeicao_plano",
    )
    op.drop_table("alimentos_refeicao_plano")
    op.drop_index(op.f("ix_refeicoes_plano_plano_id"), table_name="refeicoes_plano")
    op.drop_table("refeicoes_plano")
    op.drop_index(op.f("ix_planos_alimentares_paciente_id"), table_name="planos_alimentares")
    op.drop_index("ix_planos_alimentares_paciente_ativo", table_name="planos_alimentares")
    op.drop_table("planos_alimentares")
