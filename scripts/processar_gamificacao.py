"""Executa o fechamento diário de streak/XP; agende para 23:59 em Sao Paulo."""

from app.core.tempo import hoje_local
from app.db.session import SessionLocal
from app.services.gamificacao import processar_gamificacao_diaria


def main() -> None:
    with SessionLocal() as db:
        total = processar_gamificacao_diaria(db, hoje_local())
    print(f"Gamificacao processada para {total} pacientes.")


if __name__ == "__main__":
    main()
