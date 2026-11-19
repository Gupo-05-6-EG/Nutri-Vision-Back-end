"""Schemas Pydantic para Amizades (RF05)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.amizade import StatusAmizade


class SolicitacaoAmizadeCreate(BaseModel):
    """Payload para enviar uma nova solicitacao de amizade (o solicitante vem do token)."""

    amigo_id: int = Field(gt=0, description="Id do paciente convidado")


class RespostaSolicitacao(BaseModel):
    """Payload para aceitar ou recusar uma solicitacao (quem responde vem do token)."""

    aceitar: bool = Field(description="True para aceitar o convite, False para recusar")


class AmizadeOut(BaseModel):
    """Representacao de um registro de amizade."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    pac_id: int
    amigo_id: int
    status: StatusAmizade
    criado_em: datetime


class AmigoItem(BaseModel):
    """Item resumido de amigo/solicitacao na lista social do paciente."""

    id: int = Field(description="Id da amizade")
    paciente_id: int = Field(description="Id do outro paciente")
    nome: str | None = Field(default=None, description="Nome do outro paciente")
    username: str | None = Field(default=None, description="Nome de usuario publico")
    streak: int = Field(default=0, description="Dias consecutivos de ofensiva")
    xp: int = Field(default=0, description="XP total do outro paciente")
    status: StatusAmizade
    sou_solicitante: bool = Field(
        description="True se o paciente solicitou o convite, False se recebeu"
    )
    criado_em: datetime
