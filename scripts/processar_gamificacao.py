"""Fecha o dia da gamificacao (ofensiva e +50 XP do dia dentro da meta).

Sem argumento, fecha os dias pendentes ate ontem (dia local de Sao Paulo). Com
`--dia AAAA-MM-DD`, fecha so aquele dia. Em producao quem chama e o servico
`gamificacao` do docker-compose (scripts/agendador_gamificacao.py), as 00:05.
"""

import argparse
from datetime import date

from app.db.session import SessionLocal
from app.services.gamificacao import fechar_dias_pendentes, processar_gamificacao_diaria


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dia", type=date.fromisoformat, help="dia local AAAA-MM-DD")
    args = parser.parse_args(argv)
    with SessionLocal() as db:
        if args.dia:
            fechados = [(args.dia, processar_gamificacao_diaria(db, args.dia))]
        else:
            fechados = fechar_dias_pendentes(db)
    for dia, total in fechados:
        print(f"Gamificacao de {dia.isoformat()}: {total} pacientes processados.")
    if not fechados:
        print("Nenhum dia pendente.")


if __name__ == "__main__":
    main()
