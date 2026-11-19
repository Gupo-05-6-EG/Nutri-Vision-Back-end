"""Fuso horario oficial do sistema (B5).

O "dia" de consumo, a semana do ranking e os horarios de sugestao de refeicao
sao sempre contados no fuso local (`APP_TIMEZONE`, padrao America/Sao_Paulo).
Os instantes continuam gravados em UTC; so o recorte de dia/semana usa o fuso.

Antes as refeicoes eram recortadas em UTC: no Brasil (UTC-3), tudo o que era
registrado entre 21h e meia-noite caia no dia seguinte e sumia do "Hoje".
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.config import get_settings

FUSO = ZoneInfo(get_settings().APP_TIMEZONE)


def agora_local() -> datetime:
    return datetime.now(FUSO)


def hoje_local() -> date:
    """Data corrente no fuso oficial."""
    return agora_local().date()


def em_fuso_local(momento: datetime) -> datetime:
    """Converte para o fuso local. Sem fuso, assume que o valor esta em UTC."""
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=UTC)
    return momento.astimezone(FUSO)


def intervalo_do_dia(dia: date) -> tuple[datetime, datetime]:
    """Limites [inicio, fim) do dia local, em UTC (para consultar o banco)."""
    inicio = datetime.combine(dia, time.min, tzinfo=FUSO)
    fim = datetime.combine(dia + timedelta(days=1), time.min, tzinfo=FUSO)
    return inicio.astimezone(UTC), fim.astimezone(UTC)


def janela_semanal(referencia: datetime | None = None) -> tuple[datetime, datetime]:
    """Semana local vigente (segunda 00:00 a domingo 23:59:59.999999), em UTC."""
    agora = em_fuso_local(referencia or datetime.now(UTC))
    segunda = agora.date() - timedelta(days=agora.weekday())
    inicio = datetime.combine(segunda, time.min, tzinfo=FUSO)
    fim = datetime.combine(segunda + timedelta(days=6), time.max, tzinfo=FUSO)
    return inicio.astimezone(UTC), fim.astimezone(UTC)
