"""cria tabelas de refeicoes e itens

Task 2.1 [Back] - Modelagem de Refeicoes (RF04, RF12).

Revision ID: 50fb3bbd67e6
Revises:
Create Date: 2026-09-20 22:22:24.903086

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "50fb3bbd67e6"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "refeicoes",
        sa.Column("id", sa.Integer(), nullable=False),
        # A FK para a tabela de usuarios entra na Task 1.2, junto com o cadastro.
        sa.Column("paciente_id", sa.Integer(), nullable=False),
        sa.Column("consumida_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observacao", sa.String(length=500), nullable=True),
        sa.Column(
            "criada_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "atualizada_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refeicoes")),
    )
    op.create_index(
        op.f("ix_refeicoes_paciente_id"),
        "refeicoes",
        ["paciente_id"],
        unique=False,
    )
    # Sustenta o historico e o consumo diario: filtra por paciente e faixa de data.
    op.create_index(
        "ix_refeicoes_paciente_consumida_em",
        "refeicoes",
        ["paciente_id", "consumida_em"],
        unique=False,
    )

    op.create_table(
        "itens_refeicao",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("refeicao_id", sa.Integer(), nullable=False),
        # O alimento_id apontando para a tabela TACO entra na Task 2.2.
        sa.Column("nome_alimento", sa.String(length=160), nullable=False),
        sa.Column("quantidade_g", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("calorias_kcal", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("proteinas_g", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("carboidratos_g", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("gorduras_g", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.CheckConstraint(
            "quantidade_g > 0", name=op.f("ck_itens_refeicao_quantidade_g_positiva")
        ),
        sa.CheckConstraint(
            "calorias_kcal >= 0", name=op.f("ck_itens_refeicao_calorias_nao_negativas")
        ),
        sa.CheckConstraint(
            "proteinas_g >= 0", name=op.f("ck_itens_refeicao_proteinas_nao_negativas")
        ),
        sa.CheckConstraint(
            "carboidratos_g >= 0",
            name=op.f("ck_itens_refeicao_carboidratos_nao_negativos"),
        ),
        sa.CheckConstraint(
            "gorduras_g >= 0", name=op.f("ck_itens_refeicao_gorduras_nao_negativas")
        ),
        sa.ForeignKeyConstraint(
            ["refeicao_id"],
            ["refeicoes.id"],
            name=op.f("fk_itens_refeicao_refeicao_id_refeicoes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_itens_refeicao")),
    )
    op.create_index(
        op.f("ix_itens_refeicao_refeicao_id"),
        "itens_refeicao",
        ["refeicao_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_itens_refeicao_refeicao_id"), table_name="itens_refeicao")
    op.drop_table("itens_refeicao")
    op.drop_index("ix_refeicoes_paciente_consumida_em", table_name="refeicoes")
    op.drop_index(op.f("ix_refeicoes_paciente_id"), table_name="refeicoes")
    op.drop_table("refeicoes")
