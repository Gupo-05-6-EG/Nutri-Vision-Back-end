"""Modelos ORM.

Todo modelo novo deve ser importado aqui: o Alembic usa `Base.metadata` para
comparar o codigo com o banco, e so enxerga o que foi importado.
"""

from app.db.base import Base
from app.models.refeicao import ItemRefeicao, Refeicao

__all__ = ["Base", "ItemRefeicao", "Refeicao"]
