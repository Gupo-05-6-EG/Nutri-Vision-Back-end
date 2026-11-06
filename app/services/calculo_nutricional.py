"""Mapeamento IA -> TACO e calculo por porcao (RF03, RF20, RF21).

O de-para fica em `data/mapeamento_ia_taco.csv` (classe do modelo + metodo de
preparo -> nome exato do alimento na TACO), para ampliar sem mexer no codigo.

Formula: nutriente = valor_por_100g x gramas / 100, arredondado em 2 casas
(meio para cima). Os totais somam os itens ja arredondados, para a tabela
exibida bater com a soma das linhas.
"""

import csv
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.alimento_taco import AlimentoTaco
from app.schemas.calculo_nutricional import ItemCalculoIn

CSV_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "mapeamento_ia_taco.csv"

_CENTESIMO = Decimal("0.01")
_CAMPOS = (
    ("calorias_kcal", "kcal_100g"),
    ("proteinas_g", "prot_100g"),
    ("carboidratos_g", "carbs_100g"),
    ("gorduras_g", "gord_100g"),
)


class SemMapeamento(Exception):
    """Nao ha de-para para a combinacao classe + metodo de preparo."""

    def __init__(self, classe: str, metodo_preparo: str) -> None:
        super().__init__(f"{classe} ({metodo_preparo})")
        self.classe = classe
        self.metodo_preparo = metodo_preparo


class AlimentoTacoAusente(Exception):
    """O de-para aponta para um alimento que nao esta na tabela alimento_taco."""

    def __init__(self, nome: str) -> None:
        super().__init__(nome)
        self.nome = nome


@lru_cache
def carregar_mapeamento() -> dict[tuple[str, str], str]:
    """(classe, metodo_preparo) -> nome do alimento na TACO."""
    with CSV_PATH.open(encoding="utf-8") as arquivo:
        return {
            (linha["classe"].strip().lower(), linha["metodo_preparo"].strip().lower()): linha[
                "alimento_taco"
            ].strip()
            for linha in csv.DictReader(arquivo)
        }


def _por_porcao(valor_100g: Decimal, gramas: Decimal) -> Decimal:
    return (valor_100g * gramas / Decimal(100)).quantize(_CENTESIMO, rounding=ROUND_HALF_UP)


def calcular_refeicao(db: Session, itens: list[ItemCalculoIn]) -> dict[str, object]:
    mapeamento = carregar_mapeamento()

    nomes: list[str] = []
    for item in itens:
        nome = mapeamento.get((item.classe, item.metodo_preparo.value))
        if nome is None:
            raise SemMapeamento(item.classe, item.metodo_preparo.value)
        nomes.append(nome)

    alimentos = {
        a.nome.strip(): a
        for a in db.execute(select(AlimentoTaco).where(AlimentoTaco.nome.in_(set(nomes))))
        .scalars()
        .all()
    }

    linhas: list[dict[str, object]] = []
    totais = {campo: Decimal("0") for campo, _ in _CAMPOS}
    for item, nome in zip(itens, nomes, strict=True):
        alimento = alimentos.get(nome)
        if alimento is None:
            raise AlimentoTacoAusente(nome)
        linha: dict[str, object] = {
            "classe": item.classe,
            "metodo_preparo": item.metodo_preparo,
            "alimento_taco_id": alimento.id,
            "alimento_taco": alimento.nome.strip(),
            "gramas": item.gramas,
        }
        for campo, coluna in _CAMPOS:
            valor = _por_porcao(getattr(alimento, coluna), item.gramas)
            linha[campo] = valor
            totais[campo] += valor
        linhas.append(linha)

    return {"itens": linhas, "totais": totais}
