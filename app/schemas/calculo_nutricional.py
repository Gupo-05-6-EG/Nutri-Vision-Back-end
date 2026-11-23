"""Schemas do calculo nutricional por porcao (RF03, RF20, RF21).

Segue o contrato do resto da API: valores em `Decimal` por dentro e
**numeros** no JSON (o Pydantic serializaria Decimal como string por padrao).
"""

from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field, field_serializer, field_validator, model_validator

LIMITE_GRAMAS = Decimal("100000")


class MetodoPreparo(StrEnum):
    """Metodo de preparo usado no de-para com a TACO (a TACO tem linha separada
    para o mesmo alimento cru, cozido ou frito, com macros bem diferentes)."""

    CRU = "cru"
    COZIDO = "cozido"
    FRITO = "frito"


class ItemCalculoIn(BaseModel):
    """Um alimento com a porcao em gramas, identificado de um destes jeitos:

    - `alimento_taco_id`: o id da nossa TACO, como vem em `GET /analises/{id}`;
    - `classe` + `metodo_preparo`: convertidos pelo de-para `mapeamento_ia_taco.csv`.
    """

    alimento_taco_id: int | None = Field(
        default=None, gt=0, description="Id em `alimento_taco` (ex.: vindo da analise da foto)"
    )
    classe: str | None = Field(
        default=None, min_length=1, max_length=80, description="Classe do modelo (ex.: arroz)"
    )
    metodo_preparo: MetodoPreparo | None = None
    gramas: Decimal = Field(gt=0, le=LIMITE_GRAMAS, decimal_places=2)

    @field_validator("classe")
    @classmethod
    def normalizar_classe(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        limpo = valor.strip().lower()
        if not limpo:
            raise ValueError("classe nao pode ser vazia")
        return limpo

    @model_validator(mode="after")
    def um_jeito_de_identificar(self) -> Self:
        por_classe = self.classe is not None or self.metodo_preparo is not None
        if self.alimento_taco_id is not None:
            if por_classe:
                raise ValueError("informe alimento_taco_id ou classe + metodo_preparo, nao ambos")
        elif self.classe is None or self.metodo_preparo is None:
            raise ValueError("informe alimento_taco_id ou classe + metodo_preparo")
        return self


class CalculoNutricionalIn(BaseModel):
    itens: list[ItemCalculoIn] = Field(min_length=1)


class ItemCalculoOut(BaseModel):
    # Nulos quando o item veio por `alimento_taco_id`.
    classe: str | None
    metodo_preparo: MetodoPreparo | None
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
