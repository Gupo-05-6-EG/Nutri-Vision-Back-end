"""cria tabelas de vinculo

Task 1.4 [Back] - Mecanismo de Vinculacao (RF15).

Revision ID: 9c2f8f2d7d1a
Revises: e4cfca49122c
Create Date: 2026-10-05 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9c2f8f2d7d1a"
down_revision: str | None = "e4cfca49122c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "codigo_vinculacao",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nutricionista_id", sa.Integer(), nullable=False),
        sa.Column("nutricionista_nome", sa.String(length=160), nullable=False),
        sa.Column("nutricionista_foto_url", sa.String(length=255), nullable=True),
        sa.Column("codigo_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resgatado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paciente_id", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_codigo_vinculacao")),
        sa.UniqueConstraint("codigo_hash", name=op.f("uq_codigo_vinculacao_codigo_hash")),
    )
    op.create_index(
        "ix_codigo_vinculacao_nutricionista_status",
        "codigo_vinculacao",
        ["nutricionista_id", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_codigo_vinculacao_nutricionista_id"),
        "codigo_vinculacao",
        ["nutricionista_id"],
        unique=False,
    )

    op.create_table(
        "vinculos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nutricionista_id", sa.Integer(), nullable=False),
        sa.Column("paciente_id", sa.Integer(), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "nutricionista_id <> paciente_id",
            name=op.f("ck_vinculos_nutricionista_diferente_do_paciente"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vinculos")),
        sa.UniqueConstraint(
            "nutricionista_id",
            "paciente_id",
            name=op.f("uq_vinculos_nutricionista_paciente"),
        ),
    )
    op.create_index(
        op.f("ix_vinculos_nutricionista_id"),
        "vinculos",
        ["nutricionista_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_vinculos_paciente_id"),
        "vinculos",
        ["paciente_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_vinculos_paciente_id"), table_name="vinculos")
    op.drop_index(op.f("ix_vinculos_nutricionista_id"), table_name="vinculos")
    op.drop_table("vinculos")
    op.drop_index(op.f("ix_codigo_vinculacao_nutricionista_id"), table_name="codigo_vinculacao")
    op.drop_index("ix_codigo_vinculacao_nutricionista_status", table_name="codigo_vinculacao")
    op.drop_table("codigo_vinculacao")