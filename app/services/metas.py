"""Meta diaria unica do paciente (A4).

Antes cada tela usava uma meta diferente: o plano no "Meu plano", um valor fixo
do .env no historico e a triagem so na sessao em que foi feita. Agora tudo sai
daqui, na mesma ordem:

1. plano alimentar ativo prescrito pelo nutricionista;
2. meta da triagem (Harris-Benedict) gravada no paciente;
3. sem meta: o app pede a triagem.

Macros que o plano nao define seguem a divisao padrao de 20% proteina, 50%
carboidratos e 30% gorduras sobre as kcal.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.paciente import Paciente
from app.models.plano_alimentar import PlanoAlimentar

KCAL_POR_G_PROTEINA = Decimal("4")
KCAL_POR_G_CARBOIDRATO = Decimal("4")
KCAL_POR_G_GORDURA = Decimal("9")
DIVISAO_PADRAO = {"proteinas_g": Decimal("0.20"), "carboidratos_g": Decimal("0.50")}
DIVISAO_PADRAO_GORDURA = Decimal("0.30")
UMA_CASA = Decimal("0.1")


@dataclass(frozen=True)
class MetaDiaria:
    kcal: Decimal | None
    proteinas_g: Decimal | None
    carboidratos_g: Decimal | None
    gorduras_g: Decimal | None
    origem: str | None  # "plano", "triagem" ou None


def _gramas(kcal: Decimal, fracao: Decimal, kcal_por_g: Decimal) -> Decimal:
    return (kcal * fracao / kcal_por_g).quantize(UMA_CASA, rounding=ROUND_HALF_UP)


def plano_ativo(db: Session, paciente_id: int) -> PlanoAlimentar | None:
    return db.execute(
        select(PlanoAlimentar).where(
            PlanoAlimentar.paciente_id == paciente_id, PlanoAlimentar.ativo.is_(True)
        )
    ).scalar_one_or_none()


def _positivo(valor: Decimal | None) -> Decimal | None:
    return valor if valor is not None and valor > 0 else None


def meta_do_paciente(db: Session, paciente: Paciente) -> MetaDiaria:
    plano = plano_ativo(db, paciente.id)
    totais = plano.totais if plano is not None else {}
    kcal = _positivo(totais.get("meta_kcal"))
    origem = "plano" if kcal is not None else None
    if kcal is None:
        kcal = _positivo(Decimal(paciente.meta_kcal) if paciente.meta_kcal is not None else None)
        origem = "triagem" if kcal is not None else None
    if kcal is None:
        return MetaDiaria(None, None, None, None, None)

    def macro(chave: str, fracao: Decimal, kcal_por_g: Decimal) -> Decimal:
        do_plano = _positivo(totais.get(f"meta_{chave}")) if origem == "plano" else None
        return do_plano if do_plano is not None else _gramas(kcal, fracao, kcal_por_g)

    return MetaDiaria(
        kcal=kcal,
        proteinas_g=macro("proteinas_g", DIVISAO_PADRAO["proteinas_g"], KCAL_POR_G_PROTEINA),
        carboidratos_g=macro(
            "carboidratos_g", DIVISAO_PADRAO["carboidratos_g"], KCAL_POR_G_CARBOIDRATO
        ),
        gorduras_g=macro("gorduras_g", DIVISAO_PADRAO_GORDURA, KCAL_POR_G_GORDURA),
        origem=origem,
    )


def meta_kcal_do_paciente(db: Session, paciente: Paciente) -> Decimal | None:
    return meta_do_paciente(db, paciente).kcal
