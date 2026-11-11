"""Envia notificacoes motivacionais diarias de desafios via FCM; agende 1x ao dia."""

from datetime import UTC, datetime

from app.db.session import SessionLocal
from app.services.fcm import enviar_push_fcm
from app.services.notificacoes_desafio import processar_notificacoes_desafios


def main() -> None:
    with SessionLocal() as db:
        total = processar_notificacoes_desafios(db, datetime.now(UTC), enviar_push_fcm)
    print(f"Notificacoes motivacionais de desafios enviadas: {total}.")


if __name__ == "__main__":
    main()

