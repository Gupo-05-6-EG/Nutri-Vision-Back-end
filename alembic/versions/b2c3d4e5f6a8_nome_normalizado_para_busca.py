"""nome normalizado (sem acento) para a busca de alimentos

A busca usava ILIKE no nome: "feijao" nao encontrava "Feijão" (B4). As duas
tabelas de alimentos ganham `nome_normalizado`, preenchido pela aplicacao.

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f7
Create Date: 2026-11-19
"""

import unicodedata
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a8"
down_revision: str | None = "a1b2c3d4e5f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABELAS = ("alimento_taco", "alimento_personalizado")


def _sem_acento(texto: str | None) -> str:
    # Copia de app.core.texto.sem_acento: a migration nao importa a aplicacao.
    decomposto = unicodedata.normalize("NFKD", texto or "")
    sem_marcas = "".join(c for c in decomposto if not unicodedata.combining(c))
    return " ".join(sem_marcas.casefold().split())


def upgrade() -> None:
    conexao = op.get_bind()
    for tabela in TABELAS:
        op.add_column(tabela, sa.Column("nome_normalizado", sa.String(150), nullable=True))
        tab = sa.table(
            tabela,
            sa.column("id", sa.Integer),
            sa.column("nome", sa.String),
            sa.column("nome_normalizado", sa.String),
        )
        for id_, nome in conexao.execute(sa.select(tab.c.id, tab.c.nome)).all():
            conexao.execute(
                tab.update().where(tab.c.id == id_).values(nome_normalizado=_sem_acento(nome))
            )
        with op.batch_alter_table(tabela) as batch:
            batch.alter_column("nome_normalizado", existing_type=sa.String(150), nullable=False)
            batch.create_index(
                batch.f(f"ix_{tabela}_nome_normalizado"), ["nome_normalizado"], unique=False
            )


def downgrade() -> None:
    for tabela in TABELAS:
        with op.batch_alter_table(tabela) as batch:
            batch.drop_index(batch.f(f"ix_{tabela}_nome_normalizado"))
            batch.drop_column("nome_normalizado")
