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


class PreviaCodigoOut(BaseModel):
    """Quem gerou o codigo, mostrado ao paciente antes de criar a conta (prototipo)."""

    nutricionista: NutricionistaPublicoOut
    crn: str
    expira_em: datetime

    @field_serializer("expira_em")
    def _expira_com_fuso(self, valor: datetime) -> datetime:
        return _com_fuso(valor)


class VinculoCriadoOut(BaseModel):
    nutricionista: NutricionistaPublicoOut
    vinculado_em: datetime
    status: str = "pendente"

    @field_serializer("vinculado_em")
    def _vinculado_em_com_fuso(self, valor: datetime) -> datetime:
        return _com_fuso(valor)


class PacienteVinculadoOut(BaseModel):
    paciente_id: int
    nome: str
    email: str
    status: str
    vinculado_em: datetime

    @field_serializer("vinculado_em")
    def _data_com_fuso(self, valor: datetime) -> datetime:
        return _com_fuso(valor)


class StatusVinculoOut(BaseModel):
    vinculo_id: int
    paciente_id: int
    nutricionista_id: int
    status: str
