"""Modelos ORM.

Todo modelo novo deve ser importado aqui: o Alembic usa `Base.metadata` para
comparar o codigo com o banco, e so enxerga o que foi importado.
"""

from app.db.base import Base
from app.models.alimento_personalizado import AlimentoPersonalizado
from app.models.alimento_taco import AlimentoTaco
from app.models.amizade import Amizade, StatusAmizade
from app.models.historico_xp import HistoricoXP
from app.models.paciente import Genero, NivelAtividade, Paciente
from app.models.refeicao import ItemRefeicao, Refeicao, TipoRefeicao

__all__ = [
    "AlimentoPersonalizado",
    "AlimentoTaco",
    "Amizade",
    "Base",
    "Genero",
    "HistoricoXP",
    "ItemRefeicao",
    "NivelAtividade",
    "Paciente",
    "Refeicao",
    "StatusAmizade",
    "TipoRefeicao",
]
