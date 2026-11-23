"""Schemas da analise de fotos pela IA.

Os campos seguem o portugues do resto da API; os valores de `status`, `motivo`
e `problemas` passam como o servico de IA os devolve. Valores nutricionais sao
`Decimal` por dentro e **numeros** no JSON, como em `calculo_nutricional`.
"""

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, field_serializer


class StatusAnalise(StrEnum):
    QUEUED = "QUEUED"  # na fila, aguardando o worker da IA
    PROCESSING = "PROCESSING"  # o modelo esta analisando a foto
    DONE = "DONE"  # alimentos identificados
    NOT_ESTIMATED = "NOT_ESTIMATED"  # nao deu para estimar (ver `motivo`)
    FAILED = "FAILED"  # erro no modelo mesmo depois das novas tentativas (ver `erro`)


def _numero(valor: Decimal | None) -> float | None:
    return None if valor is None else float(valor)


class AnaliseCriadaOut(BaseModel):
    id: str = Field(description="Id da analise. Use em `GET /analises/{id}`.")
    status: StatusAnalise
    motivo: str | None = Field(
        default=None,
        description="So com `NOT_ESTIMATED`: `bad_photo`, `nothing_detected` ou `low_confidence`.",
    )
    problemas: list[str] | None = Field(
        default=None,
        description="So com `motivo=bad_photo`: `blurry`, `too_dark` e/ou `too_bright`.",
    )


class ItemAnaliseOut(BaseModel):
    """Um alimento reconhecido na foto, ligado a nossa tabela TACO quando possivel."""

    alimento: str = Field(description="Nome do alimento na TACO (ou o dado pelo modelo).")
    alimento_taco_id: int | None = Field(
        description="Id na nossa tabela `alimento_taco`; nulo quando o alimento nao esta nela.",
    )
    gramas: Decimal
    confianca: float = Field(ge=0, le=1)
    calorias_kcal: Decimal | None
    proteinas_g: Decimal | None
    carboidratos_g: Decimal | None
    gorduras_g: Decimal | None

    @field_serializer("gramas", "calorias_kcal", "proteinas_g", "carboidratos_g", "gorduras_g")
    def _numerico(self, valor: Decimal | None) -> float | None:
        return _numero(valor)


class TotaisAnalise(BaseModel):
    """Soma dos itens encontrados na TACO."""

    calorias_kcal: Decimal
    proteinas_g: Decimal
    carboidratos_g: Decimal
    gorduras_g: Decimal

    @field_serializer("calorias_kcal", "proteinas_g", "carboidratos_g", "gorduras_g")
    def _numerico(self, valor: Decimal) -> float:
        return float(valor)


class AnaliseOut(AnaliseCriadaOut):
    erro: str | None = Field(default=None, description="So com `FAILED`: o que deu errado.")
    versao_modelo: str | None = Field(default=None, description="Modelo que fez a analise.")
    itens: list[ItemAnaliseOut] | None = Field(
        default=None, description="Com `DONE` ou `NOT_ESTIMATED`: os alimentos encontrados."
    )
    totais: TotaisAnalise | None = Field(
        default=None, description="Junto com `itens`: soma dos itens encontrados na TACO."
    )
