"""merge task 1.4 heads and add foreign keys

Revision ID: a1b2c3d4e5f6
Revises: cb009bd17cf9, 9c2f8f2d7d1a
Create Date: 2026-10-05 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "a1b2c3d4e5f6"
down_revision: tuple[str, str] | None = ("cb009bd17cf9", "9c2f8f2d7d1a")
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

    with op.batch_alter_table("codigo_vinculacao") as batch_op:
        batch_op.create_foreign_key(
            batch_op.f("fk_codigo_vinculacao_nutricionista_id_nutricionistas"),
            "nutricionistas",
            ["nutricionista_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_codigo_vinculacao_paciente_id_pacientes"),
            "pacientes",
            ["paciente_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("vinculos") as batch_op:
        batch_op.create_foreign_key(
            batch_op.f("fk_vinculos_nutricionista_id_nutricionistas"),
            "nutricionistas",
            ["nutricionista_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_vinculos_paciente_id_pacientes"),
            "pacientes",
            ["paciente_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    with op.batch_alter_table("vinculos") as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_vinculos_paciente_id_pacientes"), type_="foreignkey"
        )
        batch_op.drop_constraint(
            batch_op.f("fk_vinculos_nutricionista_id_nutricionistas"),
            type_="foreignkey",
        )

    with op.batch_alter_table("codigo_vinculacao") as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_codigo_vinculacao_paciente_id_pacientes"),
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            batch_op.f("fk_codigo_vinculacao_nutricionista_id_nutricionistas"),
            type_="foreignkey",
        )

    op.drop_table("nutricionistas")
    op.drop_table("usuarios")
