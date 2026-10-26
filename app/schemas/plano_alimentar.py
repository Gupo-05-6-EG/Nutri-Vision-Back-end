"""Schemas do plano alimentar (RF09.1).

Mesmo contrato do resto da API: `Decimal` por dentro e numeros no JSON, e
instantes sempre com offset.
"""

from datetime import UTC, datetime, time
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator


def _sem_espacos_nas_pontas(valor: str, campo: str) -> str:
    limpo = valor.strip()
    if not limpo:
        raise ValueError(f"{campo} nao pode ser vazio")
    return limpo


class AlimentoPlanoIn(BaseModel):
    nome_alimento: str = Field(min_length=1, max_length=160)
    quantidade_g: Decimal = Field(gt=0, le=Decimal("5000"), decimal_places=2)
    alimento_taco_id: int | None = Field(default=None, gt=0)

    @field_validator("nome_alimento")
    @classmethod
    def _nome(cls, valor: str) -> str:
        return _sem_espacos_nas_pontas(valor, "nome_alimento")


class RefeicaoPlanoIn(BaseModel):
    nome: str = Field(min_length=1, max_length=60)
    horario: time | None = None
    meta_kcal: Decimal = Field(ge=0, le=Decimal("10000"), decimal_places=2)
    meta_proteinas_g: Decimal = Field(ge=0, le=Decimal("1000"), decimal_places=2)
    observacao: str | None = Field(default=None, max_length=500)
    alimentos: list[AlimentoPlanoIn] = Field(min_length=1, max_length=50)

    @field_validator("nome")
    @classmethod
    def _nome(cls, valor: str) -> str:
        return _sem_espacos_nas_pontas(valor, "nome")


class PlanoAlimentarIn(BaseModel):
    titulo: str = Field(min_length=1, max_length=120)
    observacao: str | None = Field(default=None, max_length=1000)
    refeicoes: list[RefeicaoPlanoIn] = Field(min_length=1, max_length=12)

    @field_validator("titulo")
    @classmethod
    def _titulo(cls, valor: str) -> str:
        return _sem_espacos_nas_pontas(valor, "titulo")


class AlimentoPlanoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome_alimento: str
    quantidade_g: Decimal
    alimento_taco_id: int | None

    @field_serializer("quantidade_g")
    def _numerico(self, valor: Decimal) -> float:
        return float(valor)


class RefeicaoPlanoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    horario: time | None
    meta_kcal: Decimal
    meta_proteinas_g: Decimal
    observacao: str | None
    alimentos: list[AlimentoPlanoOut]

    @field_serializer("meta_kcal", "meta_proteinas_g")
    def _numerico(self, valor: Decimal) -> float:
        return float(valor)


class MetasDoPlano(BaseModel):
    """Metas do dia: soma das metas dos blocos."""

    meta_kcal: Decimal
    meta_proteinas_g: Decimal

    @field_serializer("meta_kcal", "meta_proteinas_g")
    def _numerico(self, valor: Decimal) -> float:
        return float(valor)


class PlanoAlimentarOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    paciente_id: int
    nutricionista_id: int | None
    titulo: str
    observacao: str | None
    ativo: bool
    criado_em: datetime
    refeicoes: list[RefeicaoPlanoOut]
    totais: MetasDoPlano

    @field_serializer("criado_em")
    def _com_fuso(self, valor: datetime) -> datetime:
        return valor if valor.tzinfo else valor.replace(tzinfo=UTC)
