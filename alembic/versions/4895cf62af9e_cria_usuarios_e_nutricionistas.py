"""cria usuarios e nutricionistas

Task 1.2 [Back] - API de Cadastro/Login (RF13).

Tambem adiciona as FKs que ficaram pendentes nas tasks anteriores:
`pacientes.id -> usuarios.id` e `refeicoes.paciente_id -> pacientes.id`.
Um banco local com pacientes/refeicoes de teste sem usuario correspondente vai
falhar aqui; recrie o banco (`docker compose down -v`) antes de subir.

Revision ID: 4895cf62af9e
Revises: 44e69f49a2c5
Create Date: 2026-09-28 19:31:28.939064

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4895cf62af9e"
down_revision: str | None = "44e69f49a2c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "usuarios",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("senha_hash", sa.String(length=60), nullable=False),
        sa.Column("perfil", sa.String(length=20), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usuarios")),
        sa.UniqueConstraint("email", name=op.f("uq_usuarios_email")),
    )

    op.create_table(
        "nutricionistas",
        # Sem autoincrement: o id e o do usuario.
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("crn", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(
            ["id"],
            ["usuarios.id"],
            name=op.f("fk_nutricionistas_id_usuarios"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_nutricionistas")),
        sa.UniqueConstraint("crn", name=op.f("uq_nutricionistas_crn")),
    )

    with op.batch_alter_table("pacientes") as batch_op:
        batch_op.create_foreign_key(
            batch_op.f("fk_pacientes_id_usuarios"),
            "usuarios",
            ["id"],
            ["id"],
            ondelete="CASCADE",
        )

    with op.batch_alter_table("refeicoes") as batch_op:
        batch_op.create_foreign_key(
            batch_op.f("fk_refeicoes_paciente_id_pacientes"),
            "pacientes",
            ["paciente_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    with op.batch_alter_table("refeicoes") as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_refeicoes_paciente_id_pacientes"), type_="foreignkey"
        )

    with op.batch_alter_table("pacientes") as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_pacientes_id_usuarios"), type_="foreignkey")

    op.drop_table("nutricionistas")
    op.drop_table("usuarios")
