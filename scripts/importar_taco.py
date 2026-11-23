"""Importa a Tabela TACO (RF02.2) para o banco Nutricional.

Le `data/taco.csv` (590 alimentos da TACO 4a edicao, NEPA/UNICAMP - fonte:
https://github.com/raulfdm/taco-api, dados extraidos diretamente da planilha
oficial da UNICAMP) e insere um `AlimentoTaco` por linha.

Uso:
    python scripts/importar_taco.py            # importa se a tabela estiver vazia
    python scripts/importar_taco.py --recriar   # apaga tudo e reimporta

Pressupoe que as migrations ja rodaram (`alembic upgrade head`).
"""

from __future__ import annotations

import argparse
import csv
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal  # noqa: E402
from app.models.alimento_taco import AlimentoTaco  # noqa: E402

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "taco.csv"


def _ler_csv() -> list[dict[str, str]]:
    with CSV_PATH.open(encoding="utf-8") as arquivo:
        return list(csv.DictReader(arquivo))


def importar(recriar: bool = False) -> int:
    db = SessionLocal()
    try:
        total_existente = db.query(AlimentoTaco).count()

        if total_existente and not recriar:
            print(
                f"alimento_taco ja tem {total_existente} registro(s); "
                "nada a fazer (use --recriar para reimportar)."
            )
            return 0

        if total_existente and recriar:
            db.query(AlimentoTaco).delete()
            db.commit()

        linhas = _ler_csv()
        alimentos = [
            AlimentoTaco(
                nome=linha["nome"],
                categoria=linha["categoria"],
                kcal_100g=Decimal(linha["kcal_100g"]),
                carbs_100g=Decimal(linha["carbs_100g"]),
                prot_100g=Decimal(linha["prot_100g"]),
                gord_100g=Decimal(linha["gord_100g"]),
            )
            for linha in linhas
        ]
        db.add_all(alimentos)
        db.commit()

        print(f"{len(alimentos)} alimentos importados de {CSV_PATH.name}.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--recriar",
        action="store_true",
        help="apaga os registros existentes antes de reimportar",
    )
    args = parser.parse_args()
    raise SystemExit(importar(recriar=args.recriar))
