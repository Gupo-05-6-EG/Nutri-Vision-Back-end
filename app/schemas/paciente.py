"""Schemas da triagem e do teto calorico diario inicial (RF14).

Segue o contrato do resto da API: valores em `Decimal` por dentro e **numeros**
no JSON (o Pydantic serializaria Decimal como string por padrao).
"""

from decimal import Decimal

from pydantic import BaseModel, Field, field_serializer

from app.models.paciente import Genero, NivelAtividade

# Limites de sanidade (evitam typos como 800 kg ou 17 cm). Os maximos tambem
# garantem que o teto calorico caiba em numeric(6,2), o tipo de `meta_kcal`:
# 250 kg, 250 cm, 10 anos, homem, muito intenso -> ~8.900 kcal (< 9.999,99).
PESO_MIN_KG = Decimal("20")
PESO_MAX_KG = Decimal("250")
ALTURA_MIN_CM = Decimal("100")
ALTURA_MAX_CM = Decimal("250")
IDADE_MIN = 10
IDADE_MAX = 120


class TriagemIn(BaseModel):
    """Dados coletados na triagem, usados no calculo basal."""

    peso_kg: Decimal = Field(
        ge=PESO_MIN_KG, le=PESO_MAX_KG, decimal_places=2, description="Peso em quilos"
    )
    altura_cm: Decimal = Field(
        ge=ALTURA_MIN_CM, le=ALTURA_MAX_CM, decimal_places=2, description="Altura em centimetros"
    )
    idade: int = Field(ge=IDADE_MIN, le=IDADE_MAX, description="Idade em anos completos")
    genero: Genero
    nivel_atividade: NivelAtividade


class TetoCaloricoOut(BaseModel):
    """Resultado do calculo, ja salvo no paciente."""

    paciente_id: int
    tmb_kcal: Decimal
    fator_atividade: Decimal
    teto_calorico_kcal: Decimal
    origem_meta: str

    @field_serializer("tmb_kcal", "fator_atividade", "teto_calorico_kcal")
    def _numerico(self, valor: Decimal) -> float:
        return float(valor)
