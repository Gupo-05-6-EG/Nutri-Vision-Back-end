"""Schemas de alimentos personalizados e da busca unificada (RF22).

Segue o contrato do resto da API: valores em `Decimal` por dentro e
**numeros** no JSON (o Pydantic serializaria Decimal como string por padrao).
"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

# Limites de sanidade por 100g: um macro nao passa de 100g, os tres juntos
# tambem nao, e nenhum alimento passa de ~900 kcal (gordura pura).
KCAL_MAX_100G = Decimal("900")
MACRO_MAX_100G = Decimal("100")

CATEGORIA_PERSONALIZADO = "Personalizado"

_CAMPOS_NUMERICOS = ("kcal_100g", "carbs_100g", "prot_100g", "gord_100g")


class OrigemAlimento(StrEnum):
    """De qual tabela o alimento veio (os ids se repetem entre as duas)."""

    TACO = "taco"
    PERSONALIZADO = "personalizado"


class AlimentoPersonalizadoCreate(BaseModel):
    # Vem no corpo enquanto nao existe autenticacao; a Task 1.2 substitui isto
    # pelo paciente do token e a Task 1.6 aplica o controle de acesso.
    paciente_id: int = Field(gt=0)
    nome: str = Field(min_length=1, max_length=150)
    kcal_100g: Decimal = Field(ge=0, le=KCAL_MAX_100G, decimal_places=2)
    carbs_100g: Decimal = Field(ge=0, le=MACRO_MAX_100G, decimal_places=2)
    prot_100g: Decimal = Field(ge=0, le=MACRO_MAX_100G, decimal_places=2)
    gord_100g: Decimal = Field(ge=0, le=MACRO_MAX_100G, decimal_places=2)

    @field_validator("nome")
    @classmethod
    def sem_espacos_nas_pontas(cls, valor: str) -> str:
        limpo = valor.strip()
        if not limpo:
            raise ValueError("nome nao pode ser vazio")
        return limpo

    @model_validator(mode="after")
    def macros_cabem_em_100g(self) -> "AlimentoPersonalizadoCreate":
        if self.carbs_100g + self.prot_100g + self.gord_100g > MACRO_MAX_100G:
            raise ValueError("carboidratos + proteinas + gorduras nao podem passar de 100g")
        return self


class AlimentoPersonalizadoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    paciente_id: int
    nome: str
    kcal_100g: Decimal
    carbs_100g: Decimal
    prot_100g: Decimal
    gord_100g: Decimal
    criado_em: datetime

    @field_serializer(*_CAMPOS_NUMERICOS)
    def _numerico(self, valor: Decimal) -> float:
        return float(valor)


class AlimentoBuscaOut(BaseModel):
    """Item da busca unificada. `origem` + `id` identificam o alimento."""

    model_config = ConfigDict(from_attributes=True)

    origem: OrigemAlimento
    id: int
    nome: str
    categoria: str
    kcal_100g: Decimal
    carbs_100g: Decimal
    prot_100g: Decimal
    gord_100g: Decimal

    @field_serializer(*_CAMPOS_NUMERICOS)
    def _numerico(self, valor: Decimal) -> float:
        return float(valor)
