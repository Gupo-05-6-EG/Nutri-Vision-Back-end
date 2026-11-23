"""Perfil do paciente: identidade, triagem, meta unica e gamificacao (A3, A4, P1)."""

from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel, field_serializer


def _numero(valor: Decimal | None) -> float | None:
    return None if valor is None else float(valor)


class MetaDiariaOut(BaseModel):
    kcal: Decimal | None
    proteinas_g: Decimal | None
    carboidratos_g: Decimal | None
    gorduras_g: Decimal | None
    origem: str | None = None  # "plano" (nutricionista), "triagem" ou None (sem meta)

    @field_serializer("kcal", "proteinas_g", "carboidratos_g", "gorduras_g")
    def _numerico(self, valor: Decimal | None) -> float | None:
        return _numero(valor)


class GamificacaoPerfilOut(BaseModel):
    xp: int
    ofensiva: int
    bloqueios: int
    divisao: str
    proxima_divisao: str | None
    xp_para_proxima: int | None
    refeicoes_registradas: int


class NutricionistaResumo(BaseModel):
    id: int
    nome: str
    crn: str


class PlanoResumo(BaseModel):
    id: int
    titulo: str
    versao: int


class PerfilPacienteOut(BaseModel):
    paciente_id: int
    nome: str
    email: str
    membro_desde: datetime
    idade: int | None
    genero: str | None
    peso_kg: Decimal | None
    altura_cm: Decimal | None
    imc: Decimal | None
    classificacao_imc: str | None
    tmb_kcal: Decimal | None
    nivel_atividade: str | None
    fator_atividade: Decimal | None
    meta: MetaDiariaOut
    gamificacao: GamificacaoPerfilOut
    nutricionista: NutricionistaResumo | None
    # Convite resgatado e ainda nao aceito: o app oferece Aceitar/Recusar.
    vinculo_pendente: NutricionistaResumo | None = None
    plano_ativo: PlanoResumo | None

    @field_serializer("peso_kg", "altura_cm", "imc", "tmb_kcal", "fator_atividade")
    def _numerico(self, valor: Decimal | None) -> float | None:
        return _numero(valor)

    @field_serializer("membro_desde")
    def _fuso(self, valor: datetime) -> datetime:
        return valor if valor.tzinfo else valor.replace(tzinfo=UTC)
