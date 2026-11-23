"""Schema de saida do Banco Nutricional TACO (RF02.2).

Segue o contrato do resto da API: valores em `Decimal` por dentro e
**numeros** no JSON (o Pydantic serializaria Decimal como string por padrao).
"""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_serializer


class AlimentoTacoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    categoria: str
    kcal_100g: Decimal
    carbs_100g: Decimal
    prot_100g: Decimal
    gord_100g: Decimal

    @field_serializer("kcal_100g", "carbs_100g", "prot_100g", "gord_100g")
    def _numerico(self, valor: Decimal) -> float:
        return float(valor)
