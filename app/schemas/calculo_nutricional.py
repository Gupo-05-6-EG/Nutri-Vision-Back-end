"""Schemas do calculo nutricional por porcao (RF03, RF20, RF21).

Segue o contrato do resto da API: valores em `Decimal` por dentro e
**numeros** no JSON (o Pydantic serializaria Decimal como string por padrao).
"""

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, field_serializer, field_validator

LIMITE_GRAMAS = Decimal("100000")


class MetodoPreparo(StrEnum):
    """Metodo de preparo usado no de-para com a TACO (a TACO tem linha separada
    para o mesmo alimento cru, cozido ou frito, com macros bem diferentes)."""

    CRU = "cru"
    COZIDO = "cozido"
    FRITO = "frito"


class ItemCalculoIn(BaseModel):
    """Um alimento reconhecido pelo modelo de IA, com a porcao em gramas."""

    classe: str = Field(
        min_length=1, max_length=80, description="Classe devolvida pelo modelo (ex.: arroz)"
    )
    metodo_preparo: MetodoPreparo
    gramas: Decimal = Field(gt=0, le=LIMITE_GRAMAS, decimal_places=2)

    @field_validator("classe")
    @classmethod
    def normalizar_classe(cls, valor: str) -> str:
        limpo = valor.strip().lower()
        if not limpo:
            raise ValueError("classe nao pode ser vazia")
        return limpo


class CalculoNutricionalIn(BaseModel):
    itens: list[ItemCalculoIn] = Field(min_length=1)


class ItemCalculoOut(BaseModel):
    classe: str
    metodo_preparo: MetodoPreparo
    alimento_taco_id: int
    alimento_taco: str
    gramas: Decimal
    calorias_kcal: Decimal
    proteinas_g: Decimal
    carboidratos_g: Decimal
    gorduras_g: Decimal

    @field_serializer("gramas", "calorias_kcal", "proteinas_g", "carboidratos_g", "gorduras_g")
    def _numerico(self, valor: Decimal) -> float:
        return float(valor)


class TotaisCalculo(BaseModel):
    calorias_kcal: Decimal
    proteinas_g: Decimal
    carboidratos_g: Decimal
    gorduras_g: Decimal

    @field_serializer("calorias_kcal", "proteinas_g", "carboidratos_g", "gorduras_g")
    def _numerico(self, valor: Decimal) -> float:
        return float(valor)


class CalculoNutricionalOut(BaseModel):
    """Tabela nutricional da refeicao: um item por linha mais os totais."""

    itens: list[ItemCalculoOut]
    totais: TotaisCalculo
