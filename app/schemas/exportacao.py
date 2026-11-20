"""Exportacao dos dados pessoais do titular (LGPD, art. 18; RF28, RNF07).

Cada bloco tem schema proprio: antes a rota devolvia objetos do banco direto e
quebrava com 500 sempre que o titular tinha algum dado. Os dados de saude saem
decifrados, porque sao do proprio titular.
"""

from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_serializer

from app.schemas.alimento_personalizado import AlimentoPersonalizadoOut
from app.schemas.privacidade import ConsentimentoOut
from app.schemas.refeicao import RefeicaoOut


def _com_fuso(valor: datetime | None) -> datetime | None:
    if valor is None:
        return None
    return valor if valor.tzinfo else valor.replace(tzinfo=UTC)


class UsuarioExportado(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    email: str
    perfil: str
    criado_em: datetime

    @field_serializer("criado_em")
    def _fuso(self, valor: datetime) -> datetime | None:
        return _com_fuso(valor)


class PacienteExportado(BaseModel):
    """Triagem, meta e dados de gamificacao do paciente."""

    model_config = ConfigDict(from_attributes=True)

    nome: str | None
    username: str | None
    peso_kg: Decimal | None
    altura_cm: Decimal | None
    idade: int | None
    genero: str | None
    nivel_atividade: str | None
    meta_kcal: Decimal | None
    origem_meta: str | None
    streak: int
    xp: int
    bloqueios_perda: int

    @field_serializer("peso_kg", "altura_cm", "meta_kcal")
    def _numerico(self, valor: Decimal | None) -> float | None:
        return None if valor is None else float(valor)


class VinculoExportado(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    nutricionista_id: int
    paciente_id: int
    status: str
    criado_em: datetime

    @field_serializer("criado_em")
    def _fuso(self, valor: datetime) -> datetime | None:
        return _com_fuso(valor)


class HistoricoXPExportado(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    quantidade: int
    motivo: str
    criado_em: datetime

    @field_serializer("criado_em")
    def _fuso(self, valor: datetime) -> datetime | None:
        return _com_fuso(valor)


class ExportacaoDadosOut(BaseModel):
    """Tudo o que o sistema guarda sobre o titular. Blocos de paciente vem vazios para
    o nutricionista."""

    gerado_em: datetime
    usuario: UsuarioExportado
    consentimentos: list[ConsentimentoOut]
    paciente: PacienteExportado | None = None
    refeicoes: list[RefeicaoOut] = []
    alimentos_personalizados: list[AlimentoPersonalizadoOut] = []
    historico_xp: list[HistoricoXPExportado] = []
    vinculos: list[VinculoExportado]
