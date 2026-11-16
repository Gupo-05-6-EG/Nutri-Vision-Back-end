"""versao do plano alimentar e tabela de auditoria

Task 5.3 [Back] - Versionamento de Plano e Auditoria (RF08, RNF08).

- `planos_alimentares.versao`: numero sequencial por paciente. Os planos que ja
  existem recebem 1, 2, 3... na ordem em que foram criados.
- `auditorias`: quem alterou, quando, e os valores antes/depois de planos e dados
  clinicos. So passa a ser preenchida a partir desta versao: o historico de
  versoes dos planos antigos ja esta completo (cada versao e uma linha de
  `planos_alimentares`), mas os valores de antes/depois delas nao foram guardados.

Revision ID: c4d9e1f6a2b3
Revises: a8e2f4c61b07
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4d9e1f6a2b3"
down_revision: str | None = "a8e2f4c61b07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _numerar_planos_existentes() -> None:
    """Versao 1, 2, 3... por paciente, na ordem de criacao dos planos."""
    bind = op.get_bind()
    planos = sa.table(
        "planos_alimentares",
        sa.column("id", sa.Integer),
        sa.column("paciente_id", sa.Integer),
        sa.column("versao", sa.Integer),
    )
    linhas = bind.execute(
        sa.select(planos.c.id, planos.c.paciente_id).order_by(planos.c.paciente_id, planos.c.id)
    ).all()

    ultima_versao: dict[int, int] = {}
    for plano_id, paciente_id in linhas:
        ultima_versao[paciente_id] = ultima_versao.get(paciente_id, 0) + 1
        bind.execute(
            sa.update(planos).where(planos.c.id == plano_id).values(versao=ultima_versao[paciente_id])
        )


def upgrade() -> None:
    # batch_alter_table para funcionar tambem no SQLite (que nao tem ADD CONSTRAINT).
    with op.batch_alter_table("planos_alimentares") as batch_op:
        batch_op.add_column(sa.Column("versao", sa.Integer(), nullable=True))

    _numerar_planos_existentes()

    with op.batch_alter_table("planos_alimentares") as batch_op:
        batch_op.alter_column("versao", existing_type=sa.Integer(), nullable=False)
        batch_op.create_unique_constraint(
            op.f("uq_planos_alimentares_paciente_id_versao"), ["paciente_id", "versao"]
        )

    op.create_table(
        "auditorias",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("paciente_id", sa.Integer(), nullable=False),
        sa.Column("autor_id", sa.Integer(), nullable=True),
        sa.Column("entidade", sa.String(length=30), nullable=False),
        sa.Column("registro_id", sa.Integer(), nullable=False),
        sa.Column("acao", sa.String(length=20), nullable=False),
        # Cifrados (JsonCifrado): guardam copias de dados de saude.
        sa.Column("antes", sa.Text(), nullable=True),
        sa.Column("depois", sa.Text(), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["pacientes.id"],
            name=op.f("fk_auditorias_paciente_id_pacientes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["autor_id"],
            ["usuarios.id"],
            name=op.f("fk_auditorias_autor_id_usuarios"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auditorias")),
    )
    op.create_index(
        "ix_auditorias_paciente_criado_em", "auditorias", ["paciente_id", "criado_em"]
    )


def downgrade() -> None:
    op.drop_index("ix_auditorias_paciente_criado_em", table_name="auditorias")
    op.drop_table("auditorias")

    with op.batch_alter_table("planos_alimentares") as batch_op:
        batch_op.drop_constraint(op.f("uq_planos_alimentares_paciente_id_versao"), type_="unique")
        batch_op.drop_column("versao")
