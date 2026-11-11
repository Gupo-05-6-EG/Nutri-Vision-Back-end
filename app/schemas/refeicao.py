"""Schemas de entrada e saida das refeicoes (RF04, RF12).

Decisoes de contrato desta API:

- Valores nutricionais sao `Decimal` por dentro (somas exatas, sem erro de
  ponto flutuante) e **numeros** no JSON. O padrao do Pydantic seria serializar
  Decimal como string, o que obrigaria o app Flutter e o painel React a fazer
  parse de texto em todo campo numerico.
- Instantes sao gravados e devolvidos em UTC, sempre com offset explicito.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.models.refeicao import TipoRefeicao

LIMITE_NUTRICIONAL = Decimal("100000")


def _como_numero(valor: Decimal) -> float:
    """Decimal -> numero JSON.

    Duas casas decimais de dados nutricionais cabem folgadamente em float64, e
    um numero e o que os dois clientes esperam ler.
    """
    return float(valor)


class ItemRefeicaoBase(BaseModel):
    nome_alimento: str = Field(min_length=1, max_length=160)
    quantidade_g: Decimal = Field(gt=0, le=LIMITE_NUTRICIONAL, decimal_places=2)
    calorias_kcal: Decimal = Field(ge=0, le=LIMITE_NUTRICIONAL, decimal_places=2)
    proteinas_g: Decimal = Field(ge=0, le=LIMITE_NUTRICIONAL, decimal_places=2)
    carboidratos_g: Decimal = Field(ge=0, le=LIMITE_NUTRICIONAL, decimal_places=2)
    gorduras_g: Decimal = Field(ge=0, le=LIMITE_NUTRICIONAL, decimal_places=2)

    @field_validator("nome_alimento")
    @classmethod
    def sem_espacos_nas_pontas(cls, valor: str) -> str:
        limpo = valor.strip()
        if not limpo:
            raise ValueError("nome_alimento nao pode ser vazio")
        return limpo

    @field_serializer(
        "quantidade_g",
        "calorias_kcal",
        "proteinas_g",
        "carboidratos_g",
        "gorduras_g",
    )
    def _numerico(self, valor: Decimal) -> float:
        return _como_numero(valor)


class ItemRefeicaoCreate(ItemRefeicaoBase):
    pass


class ItemRefeicaoOut(ItemRefeicaoBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class TotaisNutricionais(BaseModel):
    """Soma de calorias e macros de um conjunto de itens."""

    calorias_kcal: Decimal
    proteinas_g: Decimal
    carboidratos_g: Decimal
    gorduras_g: Decimal

    @field_serializer("calorias_kcal", "proteinas_g", "carboidratos_g", "gorduras_g")
    def _numerico(self, valor: Decimal) -> float:
        return _como_numero(valor)


class RefeicaoCreate(BaseModel):
    # Ainda vem no corpo; a Task 1.6 (RNF06) passa a conferir contra o token.
    paciente_id: int = Field(gt=0)
    consumida_em: datetime
    # Cafe da manha, almoco, lanche ou jantar (RF19). Se omitido, o service
    # sugere automaticamente a partir do horario de `consumida_em`.
    tipo: TipoRefeicao | None = None
    observacao: str | None = Field(default=None, max_length=500)
    itens: list[ItemRefeicaoCreate] = Field(min_length=1)


class RefeicaoUpdate(BaseModel):
    consumida_em: datetime | None = None
    tipo: TipoRefeicao | None = None
    observacao: str | None = Field(default=None, max_length=500)
    itens: list[ItemRefeicaoCreate] | None = Field(default=None, min_length=1)


class RefeicaoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    paciente_id: int
    consumida_em: datetime
    tipo: TipoRefeicao
    observacao: str | None
    criada_em: datetime
    atualizada_em: datetime
    itens: list[ItemRefeicaoOut]
    totais: TotaisNutricionais

    @field_serializer("consumida_em", "criada_em", "atualizada_em")
    def _sempre_com_fuso(self, valor: datetime) -> datetime:
        """Garante o offset na resposta.

        Todos os instantes sao gravados em UTC. Bancos sem suporte a fuso (o
        SQLite dos testes) devolvem o valor sem `tzinfo`, e um ISO sem offset
        seria lido como hora local pelo app e pelo painel.
        """
        return valor if valor.tzinfo else valor.replace(tzinfo=UTC)


class ConsumoDiario(BaseModel):
    """Consumo de um paciente em um dia, com os totais (RF12)."""

    paciente_id: int
    data: date
    quantidade_refeicoes: int
    totais: TotaisNutricionais
    refeicoes: list[RefeicaoOut]
