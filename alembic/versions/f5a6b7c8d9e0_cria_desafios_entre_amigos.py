"""cria desafios e participantes entre pacientes

Task 4.4 [Back] - Desafios entre Amigos (RF05.2, RF05.3).

Revision ID: f5a6b7c8d9e0
Revises: a8e2f4c61b07
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f5a6b7c8d9e0"
down_revision: str | None = "a8e2f4c61b07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "desafios",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("criador_id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column("tipo", sa.String(length=30), nullable=False),
        sa.Column("regra", sa.String(length=500), nullable=False),
        sa.Column("inicio_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fim_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("fim_em > inicio_em", name=op.f("ck_desafios_datas_validas")),
        sa.CheckConstraint("criador_id > 0", name=op.f("ck_desafios_criador_positivo")),
        sa.ForeignKeyConstraint(["criador_id"], ["pacientes.id"],
                                name=op.f("fk_desafios_criador_id_pacientes"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_desafios")),
    )
    op.create_index(op.f("ix_desafios_criador_id"), "desafios", ["criador_id"], unique=False)
    op.create_table(
        "participantes_desafio",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("desafio_id", sa.Integer(), nullable=False),
        sa.Column("paciente_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="convidado", nullable=False),
        sa.Column("convidado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("respondido_em", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["desafio_id"], ["desafios.id"],
                                name=op.f("fk_participantes_desafio_desafio_id_desafios"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["paciente_id"], ["pacientes.id"],
                                name=op.f("fk_participantes_desafio_paciente_id_pacientes"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_participantes_desafio")),
        sa.UniqueConstraint("desafio_id", "paciente_id", name=op.f("uq_participantes_desafio_desafio_id")),
    )
    op.create_index(op.f("ix_participantes_desafio_desafio_id"), "participantes_desafio", ["desafio_id"], unique=False)
    op.create_index(op.f("ix_participantes_desafio_paciente_id"), "participantes_desafio", ["paciente_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_participantes_desafio_paciente_id"), table_name="participantes_desafio")
    op.drop_index(op.f("ix_participantes_desafio_desafio_id"), table_name="participantes_desafio")
    op.drop_table("participantes_desafio")
    op.drop_index(op.f("ix_desafios_criador_id"), table_name="desafios")
    op.drop_table("desafios")
