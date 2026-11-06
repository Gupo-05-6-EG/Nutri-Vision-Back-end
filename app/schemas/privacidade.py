"""Contratos de consentimento e direitos do titular."""

from datetime import datetime

from pydantic import BaseModel, Field


class ConsentimentoIn(BaseModel):
    versao_termo: str = Field(min_length=1, max_length=40, pattern=r"\S")


class ConsentimentoOut(BaseModel):
    versao_termo: str
    aceito_em: datetime
    revogado_em: datetime | None


class ConsentimentoStatusOut(BaseModel):
    consentimentos: list[ConsentimentoOut]
    consentimento_ativo: bool
