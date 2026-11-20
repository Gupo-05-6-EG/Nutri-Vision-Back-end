"""Agendador dos fechamentos diarios (servico `agendador` do docker-compose).

Funciona como um cron dentro do container. Ao subir e depois todo dia no
AGENDADOR_HORARIO (padrao 00:05, fuso APP_TIMEZONE), fecha o dia que acabou:

- gamificacao: ofensiva e +50 XP do dia dentro da meta (recupera ate 7 dias);
- alertas de desvio de meta, com a janela de dias consecutivos terminando ontem.

Cada fechamento roda separado: a falha de um vai para o log e nao impede o
outro nem derruba o servico; a proxima execucao tenta de novo.
"""

import logging
import os
import time
from datetime import datetime, timedelta

from app.core.tempo import FUSO
from app.db.session import SessionLocal
from app.services.alertas_desvio import fechar_alertas_do_dia_anterior
from app.services.gamificacao import fechar_dias_pendentes

log = logging.getLogger("agendador")


def proxima_execucao(agora: datetime, horario: str) -> datetime:
    hora, minuto = (int(parte) for parte in horario.split(":"))
    alvo = agora.replace(hour=hora, minute=minuto, second=0, microsecond=0)
    return alvo if alvo > agora else alvo + timedelta(days=1)


def _gamificacao() -> None:
    with SessionLocal() as db:
        for dia, total in fechar_dias_pendentes(db):
            log.info("gamificacao de %s: %s pacientes", dia.isoformat(), total)


def _alertas() -> None:
    with SessionLocal() as db:
        dia, total = fechar_alertas_do_dia_anterior(db)
        log.info("alertas de desvio de %s: %s gerados", dia.isoformat(), total)


FECHAMENTOS = {"gamificacao": _gamificacao, "alertas de desvio": _alertas}


def executar() -> None:
    for nome, fechamento in FECHAMENTOS.items():
        try:
            fechamento()
        except Exception:
            log.exception("falha no fechamento de %s; nova tentativa na proxima execucao", nome)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    horario = os.environ.get("AGENDADOR_HORARIO", "00:05")
    executar()
    while True:
        alvo = proxima_execucao(datetime.now(FUSO), horario)
        log.info("proximo fechamento em %s", alvo.isoformat())
        time.sleep(max(1.0, (alvo - datetime.now(FUSO)).total_seconds()))
        executar()


if __name__ == "__main__":
    main()
