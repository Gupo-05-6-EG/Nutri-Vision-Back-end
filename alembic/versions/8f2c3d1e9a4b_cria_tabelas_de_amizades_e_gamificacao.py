"""cria tabelas de amizades e gamificacao

Task 4.3 [Back] - Sistema Social e Leaderboard (RF05).

Revision ID: 8f2c3d1e9a4b
Revises: 7d1e3b9a4c20
Create Date: 2026-10-26 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8f2c3d1e9a4b"
down_revision: str | None = "7d1e3b9a4c20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Amplia a tabela de pacientes com campos de identidade social e gamificacao (DER 3.3, RF05, RF16)
    op.add_column("pacientes", sa.Column("username", sa.String(length=50), nullable=True))
    op.create_index(op.f("ix_pacientes_username"), "pacientes", ["username"], unique=True)
    op.add_column("pacientes", sa.Column("streak", sa.Integer(), server_default="0", nullable=False))
    op.add_column("pacientes", sa.Column("xp", sa.Integer(), server_default="0", nullable=False))
    op.create_check_constraint(
        op.f("ck_pacientes_streak_nao_negativo"), "pacientes", "streak >= 0"
    )
    op.create_check_constraint(
        op.f("ck_pacientes_xp_nao_negativo"), "pacientes", "xp >= 0"
    )

    # 2. Cria a tabela de amizades (DER 3.6, RF05)
    op.create_table(
        "amizades",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pac_id", sa.Integer(), nullable=False),
        sa.Column("amigo_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pendente", nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("pac_id != amigo_id", name=op.f("ck_amizades_nao_auto_amizade")),
        sa.CheckConstraint(
            "status IN ('pendente', 'aceito', 'recusado')",
            name=op.f("ck_amizades_status_valido"),
        ),
        sa.ForeignKeyConstraint(
            ["amigo_id"],
            ["pacientes.id"],
            name=op.f("fk_amizades_amigo_id_pacientes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["pac_id"],
            ["pacientes.id"],
            name=op.f("fk_amizades_pac_id_pacientes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_amizades")),
        sa.UniqueConstraint("pac_id", "amigo_id", name=op.f("uq_amizades_pac_id")),
    )
    op.create_index(op.f("ix_amizades_pac_id"), "amizades", ["pac_id"], unique=False)
    op.create_index(op.f("ix_amizades_amigo_id"), "amizades", ["amigo_id"], unique=False)

    # 3. Cria a tabela de historico de XP para calculos dinamicos de ranking temporal (RF05, RF16)
    op.create_table(
        "historico_xp",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("paciente_id", sa.Integer(), nullable=False),
        sa.Column("quantidade", sa.Integer(), nullable=False),
        sa.Column("motivo", sa.String(length=100), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "quantidade > 0", name=op.f("ck_historico_xp_quantidade_positiva")
        ),
        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["pacientes.id"],
            name=op.f("fk_historico_xp_paciente_id_pacientes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_historico_xp")),
    )
    op.create_index(
        op.f("ix_historico_xp_paciente_id"), "historico_xp", ["paciente_id"], unique=False
    )
    op.create_index(
        op.f("ix_historico_xp_criado_em"), "historico_xp", ["criado_em"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_historico_xp_criado_em"), table_name="historico_xp")
    op.drop_index(op.f("ix_historico_xp_paciente_id"), table_name="historico_xp")
    op.drop_table("historico_xp")

    op.drop_index(op.f("ix_amizades_amigo_id"), table_name="amizades")
    op.drop_index(op.f("ix_amizades_pac_id"), table_name="amizades")
    op.drop_table("amizades")

    op.drop_constraint(op.f("ck_pacientes_xp_nao_negativo"), "pacientes", type_="check")
    op.drop_constraint(op.f("ck_pacientes_streak_nao_negativo"), "pacientes", type_="check")
    op.drop_column("pacientes", "xp")
    op.drop_column("pacientes", "streak")
    op.drop_index(op.f("ix_pacientes_username"), table_name="pacientes")
    op.drop_column("pacientes", "username")
