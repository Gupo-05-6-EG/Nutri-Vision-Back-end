"""Envia os lembretes de refeicao nao registrada via FCM; agende a cada 5 minutos."""

from datetime import UTC, datetime

from app.db.session import SessionLocal
from app.services.fcm import enviar_push_fcm
from app.services.lembretes_refeicao import processar_lembretes


def main() -> None:
    with SessionLocal() as db:
        total = processar_lembretes(db, datetime.now(UTC), enviar_push_fcm)
    print(f"Lembretes de refeicao enviados: {total}.")


if __name__ == "__main__":
    main()
