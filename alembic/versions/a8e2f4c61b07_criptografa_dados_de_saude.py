"""criptografa dados de saude do paciente e observacao das refeicoes

Task 1.6 [Back] - Controle de Acesso por Perfil e Vinculo (RNF06).

Troca as colunas abaixo por TEXT e cifra (Fernet, `ENCRYPTION_KEY`) os valores que
ja existem:

- pacientes: peso_kg, altura_cm, idade, genero, nivel_atividade
- refeicoes: observacao

Os CHECKs de faixa de peso, altura e idade saem junto: o banco passa a guardar
texto cifrado e nao consegue compara-lo com numero (o schema da triagem continua
validando as faixas).

ATENCAO: o downgrade decifra com a `ENCRYPTION_KEY` atual. Sem a mesma chave da
epoca do upgrade os dados nao voltam.

Revision ID: a8e2f4c61b07
Revises: 95a3f50655d5
Create Date: 2026-11-06 14:00:00.000000

"""

from collections.abc import Callable, Sequence

import sqlalchemy as sa
from alembic import op
from app.core.crypto import cifrar, decifrar

revision: str = "a8e2f4c61b07"
down_revision: str | None = "95a3f50655d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (tabela, coluna, tipo original, expressao para voltar ao tipo original no downgrade)
COLUNAS = [
    ("pacientes", "peso_kg", sa.Numeric(precision=5, scale=2), "peso_kg::numeric(5,2)"),
    ("pacientes", "altura_cm", sa.Numeric(precision=5, scale=2), "altura_cm::numeric(5,2)"),
    ("pacientes", "idade", sa.Integer(), "idade::integer"),
    ("pacientes", "genero", sa.String(length=30), "genero"),
    ("pacientes", "nivel_atividade", sa.String(length=30), "nivel_atividade"),
    ("refeicoes", "observacao", sa.String(length=500), "observacao"),
]

# CHECKs de `pacientes` que deixam de fazer sentido com a coluna em texto cifrado.
CHECKS = [
    ("peso_kg > 0", "ck_pacientes_peso_kg_positivo"),
    ("altura_cm > 0", "ck_pacientes_altura_cm_positiva"),
    ("idade > 0", "ck_pacientes_idade_positiva"),
]


def _transformar_valores(tabela: str, coluna: str, funcao: Callable[[str], str]) -> None:
    """Aplica `funcao` ao valor de cada linha que tem a coluna preenchida."""
    conexao = op.get_bind()
    linhas = conexao.execute(
        sa.text(f"SELECT id, {coluna} FROM {tabela} WHERE {coluna} IS NOT NULL")  # noqa: S608
    ).fetchall()
    for id_, valor in linhas:
        conexao.execute(
            sa.text(f"UPDATE {tabela} SET {coluna} = :valor WHERE id = :id"),  # noqa: S608
            {"valor": funcao(str(valor)), "id": id_},
        )


def upgrade() -> None:
    for _expressao, nome in CHECKS:
        op.drop_constraint(op.f(nome), "pacientes", type_="check")

    for tabela, coluna, _tipo, _volta in COLUNAS:
        op.alter_column(
            tabela,
            coluna,
            existing_nullable=True,
            type_=sa.Text(),
            postgresql_using=f"{coluna}::text",
        )
        _transformar_valores(tabela, coluna, cifrar)


def downgrade() -> None:
    for tabela, coluna, tipo, volta in COLUNAS:
        _transformar_valores(tabela, coluna, decifrar)
        op.alter_column(
            tabela,
            coluna,
            existing_nullable=True,
            type_=tipo,
            postgresql_using=volta,
        )

    for expressao, nome in CHECKS:
        op.create_check_constraint(op.f(nome), "pacientes", expressao)
