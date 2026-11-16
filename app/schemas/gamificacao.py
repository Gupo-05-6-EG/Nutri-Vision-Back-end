"""Schemas Pydantic para Gamificacao e Leaderboard Semanal (RF05, RF16, RF29)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RegistroXPIn(BaseModel):
    """Payload para registrar ganho de experiencia (XP)."""

    paciente_id: int = Field(gt=0, description="Id do paciente beneficiado")
    quantidade: int = Field(gt=0, description="Pontos de XP a conceder")
    motivo: str = Field(min_length=1, max_length=100, description="Origem da pontuacao")


class HistoricoXPOut(BaseModel):
    """Registro individual de evento de ganho de experiencia."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    paciente_id: int
    quantidade: int
    motivo: str
    criado_em: datetime


class LeaderboardItem(BaseModel):
    """Entrada no placar semanal de amigos (RF05.3, RF29).

    Restrito a informacoes nao sensiveis (RF-29): apenas pontos de XP na semana,
    ofensiva (streak) e nome de usuario, resguardando dados de saude.
    """

    posicao: int = Field(ge=1, description="Posicao no ranking (1 a 10)")
    paciente_id: int = Field(gt=0, description="Identificador do paciente")
    username: str | None = Field(default=None, description="Nome de usuario exclusivo")
    xp_semanal: int = Field(ge=0, description="XP ganho dentro da janela semanal vigente")
    streak: int = Field(ge=0, description="Dias consecutivos de ofensiva ativa")
    e_voce: bool = Field(default=False, description="Flag indicando se o registro e do solicitante")


class LeaderboardOut(BaseModel):
    """Leaderboard de amigos com base no XP acumulado na janela semanal."""

    inicio_semana: datetime = Field(
        description="Inicio da janela semanal em UTC (Segunda-feira 00:00)"
    )
    fim_semana: datetime = Field(description="Fim da janela semanal em UTC (Domingo 23:59:59)")
    total_participantes: int = Field(
        ge=0, description="Total de participantes avaliados na rede do paciente"
    )
    posicao_solicitante: int | None = Field(
        default=None, description="Posicao do usuario solicitante no placar"
    )
    ranking: list[LeaderboardItem] = Field(
        description="Top 10 amigos ordenados por ganho de XP na janela semanal"
    )
