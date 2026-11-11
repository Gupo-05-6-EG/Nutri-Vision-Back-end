"""Contratos da API de desafios entre pacientes (RF05.2, RF05.3)."""

from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.models.desafio import StatusParticipante, TipoDesafio


class DesafioCriarIn(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    tipo: TipoDesafio
    regra: str = Field(min_length=1, max_length=500)
    inicio_em: datetime
    fim_em: datetime
    convidados: list[int] = Field(default_factory=list, max_length=50)


class ConvidarIn(BaseModel):
    pacientes: list[int] = Field(min_length=1, max_length=50)


class ResponderConviteIn(BaseModel):
    aceitar: bool


class ParticipanteOut(BaseModel):
    paciente_id: int
    nome: str
    status: StatusParticipante


class DesafioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    tipo: TipoDesafio
    regra: str
    inicio_em: datetime
    fim_em: datetime
    status: StatusParticipante | None = None

    @field_serializer("inicio_em", "fim_em")
    def com_fuso(self, valor: datetime) -> datetime:
        return valor if valor.tzinfo else valor.replace(tzinfo=UTC)


class PlacarItemOut(BaseModel):
    posicao: int
    paciente_id: int
    nome: str
    pontuacao: Decimal | None
    unidade: str

    @field_serializer("pontuacao")
    def pontuacao_numerica(self, valor: Decimal | None) -> float | None:
        return float(valor) if valor is not None else None


class PlacarOut(BaseModel):
    desafio_id: int
    tipo: TipoDesafio
    participantes: list[PlacarItemOut]
