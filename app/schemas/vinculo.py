"""Schemas do fluxo de vinculo paciente-nutricionista (Task 1.4)."""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer


def _com_fuso(valor: datetime) -> datetime:
    return valor if valor.tzinfo else valor.replace(tzinfo=UTC)


class CodigoVinculacaoCreateOut(BaseModel):
    codigo: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    status: str
    expira_em: datetime

    @field_serializer("expira_em")
    def _expira_com_fuso(self, valor: datetime) -> datetime:
        return _com_fuso(valor)


class CodigoVinculacaoIn(BaseModel):
    codigo: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class NutricionistaPublicoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    foto_url: str | None = None


class VinculoCriadoOut(BaseModel):
    nutricionista: NutricionistaPublicoOut
    vinculado_em: datetime

    @field_serializer("vinculado_em")
    def _vinculado_em_com_fuso(self, valor: datetime) -> datetime:
        return _com_fuso(valor)
