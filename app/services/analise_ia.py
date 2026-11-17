"""Resultado da analise de foto da IA ligado a nossa TACO, com as macros (RF02, RF03).

O servico de IA devolve cada alimento com o nome oficial da TACO e as gramas
estimadas. O `taco_id` dele **nao** serve aqui: a IA numera os 597 alimentos da
TACO original, e a nossa tabela `alimento_taco` tem 590 (e ids diferentes em
parte deles). Por isso o cruzamento e pelo nome normalizado.
"""

import re
import unicodedata
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.alimento_taco import AlimentoTaco
from app.services.calculo_nutricional import _CAMPOS, _por_porcao

_ESPACOS = re.compile(r"\s+")


def normalizar_nome(nome: str) -> str:
    """Forma canonica do nome para comparar: NFC, espacos unicos, sem caixa."""
    return _ESPACOS.sub(" ", unicodedata.normalize("NFC", nome)).strip().casefold()


def _taco_por_nome(db: Session) -> dict[str, AlimentoTaco]:
    alimentos: dict[str, AlimentoTaco] = {}
    for alimento in db.execute(select(AlimentoTaco).order_by(AlimentoTaco.id)).scalars():
        alimentos.setdefault(normalizar_nome(alimento.nome), alimento)
    return alimentos


def _itens(db: Session, itens_ia: list[dict[str, Any]]) -> tuple[list[dict], dict[str, Decimal]]:
    taco = _taco_por_nome(db) if itens_ia else {}
    totais = {campo: Decimal("0") for campo, _ in _CAMPOS}
    itens = []
    for item in itens_ia:
        gramas = Decimal(str(item["grams"])).quantize(Decimal("0.01"))
        alimento = taco.get(normalizar_nome(item["food"]))
        linha: dict[str, Any] = {
            "alimento": alimento.nome.strip() if alimento else item["food"],
            "alimento_taco_id": alimento.id if alimento else None,
            "gramas": gramas,
            "confianca": item["confidence"],
        }
        for campo, coluna in _CAMPOS:
            if alimento is None:
                linha[campo] = None
            else:
                valor = _por_porcao(getattr(alimento, coluna), gramas)
                linha[campo] = valor
                totais[campo] += valor
        itens.append(linha)
    return itens, totais


def montar_resultado(db: Session, analise: dict[str, Any]) -> dict[str, Any]:
    """Traduz a resposta da IA para o contrato da nossa API."""
    resultado: dict[str, Any] = {
        "id": analise["id"],
        "status": analise["status"],
        "motivo": analise.get("reason"),
        "problemas": analise.get("issues"),
        "erro": analise.get("error"),
        "versao_modelo": analise.get("model_version"),
        "itens": None,
        "totais": None,
    }
    if analise.get("items") is not None:
        resultado["itens"], resultado["totais"] = _itens(db, analise["items"])
    return resultado
