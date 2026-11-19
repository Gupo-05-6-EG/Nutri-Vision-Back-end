"""Visao geral da carteira do nutricionista (prototipo do painel: Visao Geral)."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, field_serializer

Situacao = Literal["ativo", "em_risco", "pendente"]


def _com_fuso(valor: datetime | None) -> datetime | None:
    if valor is None:
        return None
    return valor if valor.tzinfo else valor.replace(tzinfo=UTC)


class IndicadoresCarteira(BaseModel):
    pacientes_ativos: int
    pacientes_pendentes: int
    # Pacientes ativos em risco: alerta de desvio nao lido ou sem registro ha 48 h.
    alertas_criticos: int
    adesao_media_pct: float | None
    ofensiva_media_dias: float | None


class ContagemSituacoes(BaseModel):
    todos: int
    ativos: int
    em_risco: int
    pendentes: int


class UltimoRegistro(BaseModel):
    tipo: str
    em: datetime

    @field_serializer("em")
    def _fuso(self, valor: datetime) -> datetime | None:
        return _com_fuso(valor)


class PacienteMonitorado(BaseModel):
    paciente_id: int
    nome: str
    email: str
    status_vinculo: str
    vinculado_em: datetime
    situacao: Situacao
    motivo_risco: Literal["alerta_desvio", "sem_registro"] | None
    meta_kcal: Decimal | None
    consumo_hoje_kcal: Decimal
    # Dias dos ultimos 7 (completos) dentro da meta, em %. Nulo sem meta.
    adesao_semanal_pct: float | None
    ofensiva: int
    xp: int
    alertas_nao_lidos: int
    ultimo_registro: UltimoRegistro | None

    @field_serializer("meta_kcal", "consumo_hoje_kcal")
    def _numero(self, valor: Decimal | None) -> float | None:
        return None if valor is None else float(valor)

    @field_serializer("vinculado_em")
    def _fuso(self, valor: datetime) -> datetime | None:
        return _com_fuso(valor)


class VisaoGeralOut(BaseModel):
    indicadores: IndicadoresCarteira
    contagens: ContagemSituacoes
    total: int
    pagina: int
    por_pagina: int
    pacientes: list[PacienteMonitorado]
