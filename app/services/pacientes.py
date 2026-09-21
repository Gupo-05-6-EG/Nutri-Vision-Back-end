"""Regras de negocio da triagem do paciente (RF14)."""

from sqlalchemy.orm import Session

from app.models.paciente import Paciente
from app.schemas.paciente import TriagemIn
from app.services.calculo_basal import (
    calcular_teto_calorico,
    calcular_tmb,
    fator_de_atividade,
)

ORIGEM_HARRIS_BENEDICT = "harris_benedict"


def registrar_triagem(db: Session, paciente_id: int, dados: TriagemIn) -> dict[str, object]:
    """Calcula o teto calorico diario inicial e salva no paciente.

    Se o paciente ainda nao existe, ele e criado. Se ja existe, a triagem e o
    teto sao sobrescritos, entao refazer a triagem gera um novo teto.
    """
    tmb = calcular_tmb(
        peso_kg=dados.peso_kg,
        altura_cm=dados.altura_cm,
        idade=dados.idade,
        genero=dados.genero,
    )
    teto = calcular_teto_calorico(tmb, dados.nivel_atividade)

    paciente = db.get(Paciente, paciente_id)
    if paciente is None:
        paciente = Paciente(id=paciente_id)
        db.add(paciente)

    paciente.peso_kg = dados.peso_kg
    paciente.altura_cm = dados.altura_cm
    paciente.idade = dados.idade
    paciente.genero = dados.genero.value
    paciente.nivel_atividade = dados.nivel_atividade.value
    paciente.meta_kcal = teto
    paciente.origem_meta = ORIGEM_HARRIS_BENEDICT

    db.commit()
    db.refresh(paciente)

    return {
        "paciente_id": paciente.id,
        "tmb_kcal": tmb,
        "fator_atividade": fator_de_atividade(dados.nivel_atividade),
        "teto_calorico_kcal": paciente.meta_kcal,
        "origem_meta": paciente.origem_meta,
    }
