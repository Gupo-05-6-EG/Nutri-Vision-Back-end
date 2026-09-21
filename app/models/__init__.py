"""Modelos ORM.

Todo modelo novo deve ser importado aqui: o Alembic usa `Base.metadata` para
comparar o codigo com o banco, e so enxerga o que foi importado.
"""

from app.db.base import Base
from app.models.alimento_taco import AlimentoTaco
from app.models.paciente import Genero, NivelAtividade, Paciente
from app.models.refeicao import ItemRefeicao, Refeicao

__all__ = [
    "AlimentoTaco",
    "Base",
    "Genero",
    "ItemRefeicao",
    "NivelAtividade",
    "Paciente",
    "Refeicao",
]
