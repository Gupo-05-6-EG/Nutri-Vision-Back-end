"""cria tabelas de lembretes de refeicao e dispositivos push

Task 2.8 [Back] - Job de Lembretes de Refeicao (RF26).

Revision ID: d3a5c1e7f902
Revises: b7c8d9e0f123
Create Date: 2026-11-06 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d3a5c1e7f902"
down_revision: str | None = "b7c8d9e0f123"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lembretes_refeicao",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("paciente_id", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("horario", sa.Time(), nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("ultimo_envio_em", sa.Date(), nullable=True),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["pacientes.id"],
            name=op.f("fk_lembretes_refeicao_paciente_id_pacientes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lembretes_refeicao")),
        sa.UniqueConstraint("paciente_id", "tipo", name="uq_lembretes_refeicao_paciente_tipo"),
    )

    op.create_table(
        "dispositivos_push",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("paciente_id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(length=512), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["pacientes.id"],
            name=op.f("fk_dispositivos_push_paciente_id_pacientes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dispositivos_push")),
        sa.UniqueConstraint("token", name=op.f("uq_dispositivos_push_token")),
    )
    op.create_index(
        op.f("ix_dispositivos_push_paciente_id"),
        "dispositivos_push",
        ["paciente_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_dispositivos_push_paciente_id"), table_name="dispositivos_push")
    op.drop_table("dispositivos_push")
    op.drop_table("lembretes_refeicao")
