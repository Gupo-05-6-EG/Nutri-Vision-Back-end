"""Executa o job diario de alertas de desvio de meta (Task 5.4, RF10.2)."""

from app.core.tempo import hoje_local
from app.db.session import SessionLocal
from app.services.alertas_desvio import processar_alertas_desvio_diario


def main() -> None:
    with SessionLocal() as db:
        total = processar_alertas_desvio_diario(db, hoje_local())
    print(f"Alertas de desvio de meta gerados: {total}.")


if __name__ == "__main__":
    main()
