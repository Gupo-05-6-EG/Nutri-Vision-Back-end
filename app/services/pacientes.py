"""Regras de negocio da triagem do paciente (RF14)."""

from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.auditoria import EntidadeAuditada
from app.models.paciente import Paciente
from app.schemas.paciente import TriagemIn
from app.services.auditoria import registrar_auditoria
from app.services.calculo_basal import (
    calcular_teto_calorico,
    calcular_tmb,
    fator_de_atividade,
)

ORIGEM_HARRIS_BENEDICT = "harris_benedict"

# Dados clinicos que entram na auditoria (RNF08).
CAMPOS_CLINICOS = (
    "peso_kg",
    "altura_cm",
    "idade",
    "genero",
    "nivel_atividade",
    "meta_kcal",
    "origem_meta",
)


class PacienteNaoEncontrado(Exception):
    """Nao existe paciente cadastrado com o id informado."""


def _dados_clinicos(paciente: Paciente) -> dict[str, Any] | None:
    """Os dados clinicos como numeros/texto simples, ou `None` se ainda nao ha nenhum."""
    valores = {campo: getattr(paciente, campo) for campo in CAMPOS_CLINICOS}
    if all(valor is None for valor in valores.values()):
        return None
    return {
        campo: float(valor) if isinstance(valor, Decimal) else valor
        for campo, valor in valores.items()
    }


def registrar_triagem(
    db: Session, paciente_id: int, dados: TriagemIn, autor_id: int | None = None
) -> dict[str, object]:
    """Calcula o teto calorico diario inicial e salva no paciente.

    O paciente nasce no cadastro (RF13). Refazer a triagem sobrescreve os dados
    e gera um novo teto. Cada mudanca real nos dados clinicos entra na auditoria
    (RNF08) com os valores de antes e depois, feita por `autor_id`; refazer a
    triagem com os mesmos valores nao gera registro.
    """
    paciente = db.get(Paciente, paciente_id)
    if paciente is None:
        raise PacienteNaoEncontrado
    antes = _dados_clinicos(paciente)

    tmb = calcular_tmb(
        peso_kg=dados.peso_kg,
        altura_cm=dados.altura_cm,
        idade=dados.idade,
        genero=dados.genero,
    )
    teto = calcular_teto_calorico(tmb, dados.nivel_atividade)

    paciente.peso_kg = dados.peso_kg
    paciente.altura_cm = dados.altura_cm
    paciente.idade = dados.idade
    paciente.genero = dados.genero.value
    paciente.nivel_atividade = dados.nivel_atividade.value
    paciente.meta_kcal = teto
    paciente.origem_meta = ORIGEM_HARRIS_BENEDICT

    depois = _dados_clinicos(paciente)
    if depois is not None and depois != antes:
        registrar_auditoria(
            db,
            paciente_id=paciente_id,
            autor_id=autor_id,
            entidade=EntidadeAuditada.DADOS_CLINICOS,
            registro_id=paciente_id,
            antes=antes,
            depois=depois,
        )

    db.commit()
    db.refresh(paciente)

    return {
        "paciente_id": paciente.id,
        "tmb_kcal": tmb,
        "fator_atividade": fator_de_atividade(dados.nivel_atividade),
        "teto_calorico_kcal": paciente.meta_kcal,
        "origem_meta": paciente.origem_meta,
    }
