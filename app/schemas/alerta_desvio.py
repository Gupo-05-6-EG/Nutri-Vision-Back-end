"""Schemas de regras e alertas de desvio de meta (Task 5.4, RF10.2)."""

from datetime import UTC, date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.models.alerta_desvio import DirecaoDesvio


class RegraAlertaDesvioIn(BaseModel):
    """Regra configuravel pelo nutricionista."""

    percentual_desvio: Decimal = Field(
        default=Decimal("20.00"),
        gt=Decimal("0"),
        le=Decimal("100"),
        decimal_places=2,
        description="Limiar percentual acima ou abaixo da meta diaria (ex.: 20 para >20%).",
    )
    dias_consecutivos: int = Field(
        default=3,
        ge=1,
        le=30,
        description="Quantidade de dias consecutivos fora da faixa para disparar o alerta.",
    )
    ativo: bool = True


class RegraAlertaDesvioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    nutricionista_id: int
    percentual_desvio: Decimal
    dias_consecutivos: int
    ativo: bool

    @field_serializer("percentual_desvio")
    def _numerico(self, valor: Decimal) -> float:
        return float(valor)


class AlertaDesvioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nutricionista_id: int
    paciente_id: int
    paciente_nome: str
    paciente_email: str
    data_referencia: date
    direcao: DirecaoDesvio
    dias_consecutivos: int
    percentual_limite: Decimal
    percentual_medio_desvio: Decimal
    meta_kcal: Decimal
    consumo_medio_kcal: Decimal
    lido: bool
    notificado_em: datetime | None
    criado_em: datetime

    @field_serializer(
        "percentual_limite",
        "percentual_medio_desvio",
        "meta_kcal",
        "consumo_medio_kcal",
    )
    def _numerico(self, valor: Decimal) -> float:
        return float(valor)

    @field_serializer("notificado_em", "criado_em")
    def _com_fuso(self, valor: datetime | None) -> datetime | None:
        if valor is None:
            return None
        return valor if valor.tzinfo else valor.replace(tzinfo=UTC)


class ProcessamentoAlertasOut(BaseModel):
    """Resumo da execucao do processamento de desvios."""

    data_referencia: date
    alertas_gerados: int
