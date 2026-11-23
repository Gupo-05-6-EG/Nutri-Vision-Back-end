"""Calculo do teto calorico diario inicial (RF14).

Duas etapas:

1. TMB (taxa metabolica basal) pela equacao de Harris-Benedict original (1919).
2. Teto calorico diario = TMB x fator do nivel de atividade fisica.

Tudo em `Decimal`, como no resto da API: o resultado e gravado em `numeric(6,2)`
e as contas ficam exatas, sem erro de ponto flutuante.

Este modulo nao acessa o banco. A persistencia fica em `services/pacientes.py`.
Para trocar pela versao revisada da equacao (Roza & Shizgal, 1984), basta
ajustar `COEFICIENTES`.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import NamedTuple

from app.models.paciente import Genero, NivelAtividade

DUAS_CASAS = Decimal("0.01")


class Coeficientes(NamedTuple):
    """TMB = base + peso x kg + altura x cm - idade x anos."""

    base: Decimal
    peso: Decimal
    altura: Decimal
    idade: Decimal


# Harris-Benedict original (1919), em kcal/dia.
COEFICIENTES: dict[Genero, Coeficientes] = {
    Genero.MASCULINO: Coeficientes(
        base=Decimal("66.47"),
        peso=Decimal("13.75"),
        altura=Decimal("5.003"),
        idade=Decimal("6.755"),
    ),
    Genero.FEMININO: Coeficientes(
        base=Decimal("655.1"),
        peso=Decimal("9.563"),
        altura=Decimal("1.850"),
        idade=Decimal("4.676"),
    ),
}

# Fatores de atividade usualmente combinados com a TMB para obter o gasto diario.
FATORES_ATIVIDADE: dict[NivelAtividade, Decimal] = {
    NivelAtividade.SEDENTARIO: Decimal("1.2"),
    NivelAtividade.LEVE: Decimal("1.375"),
    NivelAtividade.MODERADO: Decimal("1.55"),
    NivelAtividade.INTENSO: Decimal("1.725"),
    NivelAtividade.MUITO_INTENSO: Decimal("1.9"),
}


def _arredondar(valor: Decimal) -> Decimal:
    """Duas casas decimais, arredondando .5 para cima."""
    return valor.quantize(DUAS_CASAS, rounding=ROUND_HALF_UP)


def calcular_tmb(*, peso_kg: Decimal, altura_cm: Decimal, idade: int, genero: Genero) -> Decimal:
    """Taxa metabolica basal (kcal/dia) pela equacao de Harris-Benedict."""
    c = COEFICIENTES[genero]
    tmb = c.base + c.peso * peso_kg + c.altura * altura_cm - c.idade * idade
    return _arredondar(tmb)


def fator_de_atividade(nivel: NivelAtividade) -> Decimal:
    return FATORES_ATIVIDADE[nivel]


def calcular_teto_calorico(tmb_kcal: Decimal, nivel: NivelAtividade) -> Decimal:
    """Teto calorico diario (kcal/dia): TMB x fator de atividade.

    Parte da TMB ja arredondada, para os numeros devolvidos pela API baterem
    entre si (`tmb_kcal` x `fator_atividade` = `teto_calorico_kcal`).
    """
    return _arredondar(tmb_kcal * fator_de_atividade(nivel))
