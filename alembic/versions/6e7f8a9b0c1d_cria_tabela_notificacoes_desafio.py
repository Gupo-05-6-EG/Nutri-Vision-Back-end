"""cria tabela de notificacoes motivacionais de desafios

Task 4.5 [Back] - Notificacoes Motivacionais de Desafios via FCM (RF05.5).

Revision ID: 6e7f8a9b0c1d
Revises: f5a6b7c8d9e0
Create Date: 2026-11-11 16:50:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6e7f8a9b0c1d"
down_revision: str | None = "f5a6b7c8d9e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notificacoes_desafio",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("paciente_id", sa.Integer(), nullable=False),
        sa.Column("desafio_id", sa.Integer(), nullable=False),
        sa.Column("posicao", sa.Integer(), nullable=False),
        sa.Column("dias_restantes", sa.Integer(), nullable=False),
        sa.Column("enviado_em", sa.Date(), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "posicao >= 1", name=op.f("ck_notificacoes_desafio_posicao_positiva")
        ),
        sa.CheckConstraint(
            "dias_restantes >= 0",
            name=op.f("ck_notificacoes_desafio_dias_restantes_nao_negativos"),
        ),
        sa.ForeignKeyConstraint(
            ["desafio_id"],
            ["desafios.id"],
            name=op.f("fk_notificacoes_desafio_desafio_id_desafios"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["pacientes.id"],
            name=op.f("fk_notificacoes_desafio_paciente_id_pacientes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notificacoes_desafio")),
        sa.UniqueConstraint(
            "paciente_id",
            "enviado_em",
            name="uq_notificacoes_desafio_paciente_dia",
        ),
    )
    op.create_index(
        op.f("ix_notificacoes_desafio_paciente_id"),
        "notificacoes_desafio",
        ["paciente_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notificacoes_desafio_desafio_id"),
        "notificacoes_desafio",
        ["desafio_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_notificacoes_desafio_desafio_id"), table_name="notificacoes_desafio"
    )
    op.drop_index(
        op.f("ix_notificacoes_desafio_paciente_id"), table_name="notificacoes_desafio"
    )
    op.drop_table("notificacoes_desafio")

