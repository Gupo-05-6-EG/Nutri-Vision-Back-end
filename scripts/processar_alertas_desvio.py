"""Fecha os alertas de desvio de meta (Task 5.4, RF10.2).

Sem argumento, avalia a janela que termina ontem (dia local de Sao Paulo); com
`--dia AAAA-MM-DD`, a que termina naquele dia. Em producao quem chama e o
servico `agendador` do docker-compose (scripts/agendador.py), as 00:05.
"""

import argparse
from datetime import date

from app.db.session import SessionLocal
from app.services.alertas_desvio import (
    fechar_alertas_do_dia_anterior,
    processar_alertas_desvio_diario,
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dia", type=date.fromisoformat, help="ultimo dia da janela")
    args = parser.parse_args(argv)
    with SessionLocal() as db:
        if args.dia:
            dia, total = args.dia, processar_alertas_desvio_diario(db, args.dia)
        else:
            dia, total = fechar_alertas_do_dia_anterior(db)
    print(f"Alertas de desvio de {dia.isoformat()}: {total} gerados.")


if __name__ == "__main__":
    main()
