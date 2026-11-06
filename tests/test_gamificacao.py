"""Testes do fechamento diario de streak e XP (RF16)."""

from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.paciente import Paciente
from app.models.refeicao import ItemRefeicao, Refeicao, TipoRefeicao
from app.services.gamificacao import FUSO_HORARIO, XP_POR_DIA, processar_gamificacao_diaria
from tests import factories

DIA = date(2026, 10, 12)


def _paciente(db: Session, paciente_id: int = 1, meta: str | None = "2000") -> Paciente:
    paciente = factories.criar_paciente(db, paciente_id)
    paciente.meta_kcal = Decimal(meta) if meta is not None else None
    db.commit()
    return paciente


def _refeicao(db: Session, paciente_id: int, hora: int, kcal: str, dia: date = DIA) -> None:
    db.add(
        Refeicao(
            paciente_id=paciente_id,
            consumida_em=datetime.combine(dia, time(hora), tzinfo=FUSO_HORARIO),
            tipo=TipoRefeicao.LANCHE.value,
            itens=[
                ItemRefeicao(
                    nome_alimento="Item",
                    quantidade_g=Decimal("100"),
                    calorias_kcal=Decimal(kcal),
                    proteinas_g=Decimal("0"),
                    carboidratos_g=Decimal("0"),
                    gorduras_g=Decimal("0"),
                )
            ],
        )
    )
    db.commit()


def test_dia_valido_soma_streak_e_xp(db: Session) -> None:
    paciente = _paciente(db)
    _refeicao(db, 1, 8, "200")
    _refeicao(db, 1, 12, "300")  # 500 kcal <= 30% de 2000

    assert processar_gamificacao_diaria(db, DIA) == 1

    assert paciente.streak == 1
    assert paciente.xp == XP_POR_DIA
    assert paciente.gamificacao_processada_em == DIA


def test_uma_refeicao_so_zera_streak_e_mantem_xp(db: Session) -> None:
    paciente = _paciente(db)
    paciente.streak, paciente.xp = 3, 150
    db.commit()
    _refeicao(db, 1, 8, "200")

    processar_gamificacao_diaria(db, DIA)

    assert paciente.streak == 0
    assert paciente.xp == 150


def test_acima_do_limite_da_meta_zera_streak(db: Session) -> None:
    paciente = _paciente(db)
    paciente.streak = 2
    db.commit()
    _refeicao(db, 1, 8, "400")
    _refeicao(db, 1, 12, "300")  # 700 kcal > 600

    processar_gamificacao_diaria(db, DIA)

    assert paciente.streak == 0


def test_paciente_sem_meta_nao_cumpre(db: Session) -> None:
    paciente = _paciente(db, meta=None)
    _refeicao(db, 1, 8, "100")
    _refeicao(db, 1, 12, "100")

    processar_gamificacao_diaria(db, DIA)

    assert paciente.streak == 0
    assert paciente.xp == 0


def test_considera_o_dia_no_fuso_de_sao_paulo(db: Session) -> None:
    paciente = _paciente(db)
    # 22h em Sao Paulo ja e o dia seguinte em UTC, mas conta para DIA.
    _refeicao(db, 1, 21, "100")
    _refeicao(db, 1, 22, "100")

    processar_gamificacao_diaria(db, DIA)

    assert paciente.streak == 1


def test_rodar_duas_vezes_no_mesmo_dia_nao_credita_de_novo(db: Session) -> None:
    paciente = _paciente(db)
    _refeicao(db, 1, 8, "100")
    _refeicao(db, 1, 12, "100")

    processar_gamificacao_diaria(db, DIA)
    assert processar_gamificacao_diaria(db, DIA) == 0

    assert paciente.streak == 1
    assert paciente.xp == XP_POR_DIA
