"""Modelo de Paciente e enums da triagem (RF14).

Escopo desta task: os dados da triagem (usados no calculo basal) e o teto
calorico diario gerado a partir deles. Campos do DER que pertencem a outras
tasks (`streak`, `xp`, `meta_dias`, `treino`, ...) entram por migration depois:

- FK de `id` para a tabela de usuarios -> Task 1.2 (RF13)

`meta_kcal` guarda o teto calorico diario vigente e `origem_meta` diz de onde ele
veio (hoje so `harris_benedict`), como previsto no DER.
"""

from datetime import date
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import CheckConstraint, Date, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Genero(StrEnum):
    """Sexo usado na equacao de Harris-Benedict (que so define dois conjuntos)."""

    MASCULINO = "masculino"
    FEMININO = "feminino"


class NivelAtividade(StrEnum):
    """Nivel de atividade fisica, que define o fator multiplicador da TMB."""

    SEDENTARIO = "sedentario"
    LEVE = "leve"
    MODERADO = "moderado"
    INTENSO = "intenso"
    MUITO_INTENSO = "muito_intenso"


class Paciente(Base):
    """Dados de triagem de um paciente e o teto calorico diario inicial."""

    __tablename__ = "pacientes"
    __table_args__ = (
        CheckConstraint("peso_kg > 0", name="peso_kg_positivo"),
        CheckConstraint("altura_cm > 0", name="altura_cm_positiva"),
        CheckConstraint("idade > 0", name="idade_positiva"),
        CheckConstraint("meta_kcal >= 0", name="meta_kcal_nao_negativa"),
        CheckConstraint("streak >= 0", name="streak_nao_negativa"),
        CheckConstraint("xp >= 0", name="xp_nao_negativo"),
    )

    # Sem autoincrement: o id do paciente e o id do usuario (Task 1.2 adiciona a
    # FK para a tabela de usuarios por migration).
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)

    # Tudo opcional porque o cadastro (Task 1.2) cria o paciente antes da triagem.
    peso_kg: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    altura_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    idade: Mapped[int | None] = mapped_column(Integer, nullable=True)
    genero: Mapped[str | None] = mapped_column(String(30), nullable=True)
    nivel_atividade: Mapped[str | None] = mapped_column(String(30), nullable=True)

    meta_kcal: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    origem_meta: Mapped[str | None] = mapped_column(String(30), nullable=True)

    streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    xp: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    gamificacao_processada_em: Mapped[date | None] = mapped_column(Date, nullable=True)
