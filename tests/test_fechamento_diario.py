"""Fechamento diario da ofensiva: meta unica, dias pendentes e agendador (BE-16)."""

from contextlib import nullcontext
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models.paciente import Paciente
from app.models.plano_alimentar import PlanoAlimentar, RefeicaoPlano
from app.models.refeicao import ItemRefeicao, Refeicao, TipoRefeicao
from app.services import gamificacao
from app.services.gamificacao import (
    FUSO_HORARIO,
    XP_POR_DIA,
    fechar_dias_pendentes,
    processar_gamificacao_diaria,
)
from scripts import agendador_gamificacao, processar_gamificacao
from tests import factories

DIA = date(2026, 11, 18)


def _paciente(db: Session, pid: int = 1, meta: str = "2900") -> Paciente:
    paciente = factories.criar_paciente(db, pid)
    paciente.meta_kcal = Decimal(meta)
    db.commit()
    return paciente


def _plano(db: Session, pid: int, kcal: str) -> None:
    db.add(
        PlanoAlimentar(
            paciente_id=pid,
            versao=1,
            titulo="Plano",
            ativo=True,
            refeicoes=[
                RefeicaoPlano(
                    ordem=1, nome="Almoco", meta_kcal=Decimal(kcal), meta_proteinas_g=Decimal("50")
                )
            ],
        )
    )
    db.commit()


def _refeicoes(db: Session, pid: int, kcal: str, dia: date = DIA) -> None:
    for hora in (8, 12):
        db.add(
            Refeicao(
                paciente_id=pid,
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


def test_ofensiva_usa_a_meta_do_plano_e_nao_a_da_triagem(db: Session) -> None:
    """Triagem de 2.900 kcal, plano de 1.000 kcal: comer o plano conta o dia."""
    paciente = _paciente(db)
    _plano(db, 1, "1000")
    _refeicoes(db, 1, "500")

    processar_gamificacao_diaria(db, DIA)

    assert paciente.streak == 1
    assert paciente.xp == XP_POR_DIA


def test_sem_plano_continua_valendo_a_triagem(db: Session) -> None:
    paciente = _paciente(db, meta="1000")
    _refeicoes(db, 1, "500")

    processar_gamificacao_diaria(db, DIA)

    assert paciente.streak == 1


def test_fecha_os_dias_pendentes_em_ordem_ate_ontem(db: Session) -> None:
    paciente = _paciente(db, meta="1000")
    paciente.gamificacao_processada_em = DIA - timedelta(days=3)
    db.commit()
    for atraso in (2, 1, 0):
        _refeicoes(db, 1, "500", DIA - timedelta(days=atraso))

    fechados = fechar_dias_pendentes(db, ate=DIA)

    assert [dia for dia, _ in fechados] == [DIA - timedelta(days=2), DIA - timedelta(days=1), DIA]
    assert paciente.streak == 3
    assert paciente.gamificacao_processada_em == DIA


def test_dia_ja_fechado_nao_e_fechado_de_novo(db: Session) -> None:
    paciente = _paciente(db, meta="1000")
    paciente.gamificacao_processada_em = DIA
    db.commit()

    assert fechar_dias_pendentes(db, ate=DIA) == []


def test_recupera_no_maximo_o_limite_de_dias(db: Session) -> None:
    paciente = _paciente(db, meta="1000")
    paciente.gamificacao_processada_em = DIA - timedelta(days=30)
    db.commit()

    fechados = fechar_dias_pendentes(db, ate=DIA, limite_dias=7)

    assert len(fechados) == 7
    assert fechados[0][0] == DIA - timedelta(days=6)


def test_sem_nada_processado_fecha_so_ontem(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _paciente(db, meta="1000")
    monkeypatch.setattr(gamificacao, "hoje_local", lambda: DIA + timedelta(days=1))

    assert [dia for dia, _ in fechar_dias_pendentes(db)] == [DIA]


def test_script_fecha_um_dia_informado(
    db: Session, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _paciente(db, meta="1000")
    monkeypatch.setattr(processar_gamificacao, "SessionLocal", lambda: nullcontext(db))

    processar_gamificacao.main(["--dia", DIA.isoformat()])
    processar_gamificacao.main([])

    saida = capsys.readouterr().out
    assert f"Gamificacao de {DIA.isoformat()}: 1 pacientes processados." in saida


def test_script_sem_dias_pendentes(
    db: Session, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(processar_gamificacao, "SessionLocal", lambda: nullcontext(db))
    monkeypatch.setattr(processar_gamificacao, "fechar_dias_pendentes", lambda _db: [])

    processar_gamificacao.main([])

    assert "Nenhum dia pendente." in capsys.readouterr().out


def test_agendador_calcula_a_proxima_execucao() -> None:
    antes = datetime(2026, 11, 19, 0, 1, tzinfo=FUSO_HORARIO)
    depois = datetime(2026, 11, 19, 15, 0, tzinfo=FUSO_HORARIO)

    assert agendador_gamificacao.proxima_execucao(antes, "00:05") == antes.replace(minute=5)
    assert agendador_gamificacao.proxima_execucao(depois, "00:05") == datetime(
        2026, 11, 20, 0, 5, tzinfo=FUSO_HORARIO
    )


def test_agendador_executa_e_nao_cai_com_erro(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    paciente = _paciente(db, meta="1000")
    _refeicoes(db, 1, "500")
    monkeypatch.setattr(agendador_gamificacao, "SessionLocal", lambda: nullcontext(db))
    monkeypatch.setattr(
        agendador_gamificacao, "fechar_dias_pendentes", lambda s: fechar_dias_pendentes(s, ate=DIA)
    )
    agendador_gamificacao.executar()
    assert paciente.streak == 1

    def falha(_db: Session) -> list:
        raise RuntimeError("banco fora")

    monkeypatch.setattr(agendador_gamificacao, "fechar_dias_pendentes", falha)
    agendador_gamificacao.executar()  # registra no log e segue


def test_agendador_roda_ao_subir_e_depois_no_horario(monkeypatch: pytest.MonkeyPatch) -> None:
    chamadas = []
    monkeypatch.setattr(agendador_gamificacao, "executar", lambda: chamadas.append("x"))

    def dormir(segundos: float) -> None:
        assert segundos >= 1
        if len(chamadas) >= 2:
            raise KeyboardInterrupt

    monkeypatch.setattr(agendador_gamificacao.time, "sleep", dormir)
    with pytest.raises(KeyboardInterrupt):
        agendador_gamificacao.main()

    assert len(chamadas) == 2
