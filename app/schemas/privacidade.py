"""Contratos de privacidade (LGPD): consentimento e direitos do titular, e DTOs publicos
de ranking/desafio expondo apenas nome, avatar, pontos e streak (RF29, RNF06, RNF07).
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ConsentimentoIn(BaseModel):
    versao_termo: str = Field(min_length=1, max_length=40, pattern=r"\S")


class ConsentimentoOut(BaseModel):
    versao_termo: str
    aceito_em: datetime
    revogado_em: datetime | None


class ConsentimentoStatusOut(BaseModel):
    consentimentos: list[ConsentimentoOut]
    consentimento_ativo: bool


class RankingPublicoItem(BaseModel):
    """DTO publico para item de ranking/leaderboard (LGPD / RF29).

    Restrito com extra='forbid' para expor estritamente:
    nome, avatar, pontos e streak.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    nome: str | None = Field(
        default=None, description="Nome de exibicao ou username publico do usuario"
    )
    avatar: str | None = Field(
        default=None, description="Identificador ou URL publica do avatar do usuario"
    )
    pontos: int = Field(ge=0, description="Pontuacao acumulada no ranking (ex: XP semanal)")
    streak: int = Field(ge=0, description="Dias consecutivos de ofensiva ativa")


class DesafioPublicoItem(BaseModel):
    """DTO publico para participantes em desafios coletivos (LGPD / RF29).

    Restrito com extra='forbid' para expor estritamente:
    nome, avatar, pontos e streak.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    nome: str | None = Field(
        default=None, description="Nome de exibicao ou username publico do participante"
    )
    avatar: str | None = Field(
        default=None, description="Identificador ou URL publica do avatar do participante"
    )
    pontos: int = Field(ge=0, description="Pontuacao acumulada no desafio")
    streak: int = Field(ge=0, description="Dias consecutivos de ofensiva ativa")


class RankingPublicoOut(BaseModel):
    """Resposta agregada para ranking publico entre amigos (LGPD / RF29)."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    total_participantes: int = Field(
        ge=0, description="Total de participantes avaliados na rede do paciente"
    )
    ranking: list[RankingPublicoItem] = Field(
        description="Placar de participantes contendo estritamente dados publicos nao sensiveis"
    )


class DesafioPublicoOut(BaseModel):
    """Resposta agregada para desafio publico entre participantes (LGPD / RF29)."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    desafio_id: int = Field(gt=0, description="Identificador unico do desafio")
    titulo: str = Field(description="Titulo ou objetivo do desafio")
    total_participantes: int = Field(
        ge=0, description="Total de participantes avaliados no desafio"
    )
    participantes: list[DesafioPublicoItem] = Field(
        description="Lista de participantes contendo estritamente dados publicos nao sensiveis"
    )
