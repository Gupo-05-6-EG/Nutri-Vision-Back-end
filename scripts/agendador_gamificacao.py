"""Agendador do fechamento diario da gamificacao (servico `gamificacao`).

Funciona como um cron dentro do container: ao subir, fecha os dias pendentes;
depois dorme ate o proximo GAMIFICACAO_HORARIO (padrao 00:05, fuso APP_TIMEZONE)
e fecha o dia que acabou. Uma falha e registrada no log e tentada de novo na
proxima execucao, sem derrubar o servico.
"""

import logging
import os
import time
from datetime import datetime, timedelta

from app.core.tempo import FUSO
from app.db.session import SessionLocal
from app.services.gamificacao import fechar_dias_pendentes

log = logging.getLogger("agendador_gamificacao")


def proxima_execucao(agora: datetime, horario: str) -> datetime:
    hora, minuto = (int(parte) for parte in horario.split(":"))
    alvo = agora.replace(hour=hora, minute=minuto, second=0, microsecond=0)
    return alvo if alvo > agora else alvo + timedelta(days=1)


def executar() -> None:
    try:
        with SessionLocal() as db:
            for dia, total in fechar_dias_pendentes(db):
                log.info("gamificacao de %s: %s pacientes", dia.isoformat(), total)
    except Exception:
        log.exception("falha no fechamento diario; nova tentativa na proxima execucao")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    horario = os.environ.get("GAMIFICACAO_HORARIO", "00:05")
    executar()
    while True:
        alvo = proxima_execucao(datetime.now(FUSO), horario)
        log.info("proximo fechamento em %s", alvo.isoformat())
        time.sleep(max(1.0, (alvo - datetime.now(FUSO)).total_seconds()))
        executar()


if __name__ == "__main__":
    main()
