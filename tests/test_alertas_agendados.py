"""Alertas de desvio fechados com dias completos e agendados (BE-19)."""

from contextlib import nullcontext
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.alerta_desvio import AlertaDesvioPlano, RegraAlertaDesvio
from app.models.refeicao import ItemRefeicao, Refeicao
from app.models.vinculo import Vinculo
from app.services import alertas_desvio
from app.services.gamificacao import FUSO_HORARIO
from scripts import agendador, processar_alertas_desvio
from tests.factories import criar_nutricionista, criar_paciente, headers_de

HOJE = date(2026, 11, 20)
ONTEM = HOJE - timedelta(days=1)


@pytest.fixture(autouse=True)
def _hoje_fixo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.core.tempo.hoje_local", lambda: HOJE)


def _paciente_vinculado(db: Session, meta: str = "2000") -> None:
    criar_nutricionista(db, 100)
    paciente = criar_paciente(db, 1)
    paciente.meta_kcal = Decimal(meta)
    db.add(Vinculo(nutricionista_id=100, paciente_id=1, status="ativo"))
    db.add(
        RegraAlertaDesvio(
            nutricionista_id=100, percentual_desvio=Decimal("20"), dias_consecutivos=2, ativo=True
        )
    )
    db.commit()


def _consumo(db: Session, dia: date, kcal: str, hora: int = 12) -> None:
    db.add(
        Refeicao(
            paciente_id=1,
            consumida_em=datetime.combine(dia, time(hora), tzinfo=FUSO_HORARIO),
            tipo="almoco",
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


def _processar(client: TestClient) -> dict:
    resposta = client.post(
        "/api/v1/alertas-desvio/processar", headers=headers_de(100, "nutricionista")
    )
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def test_exagero_ontem_e_anteontem_gera_alerta_sem_registro_hoje(
    client: TestClient, db: Session
) -> None:
    _paciente_vinculado(db)
    _consumo(db, ONTEM - timedelta(days=1), "2700")
    _consumo(db, ONTEM, "2800")

    assert _processar(client) == {"data_referencia": ONTEM.isoformat(), "alertas_gerados": 1}


def test_dia_de_hoje_pela_metade_nao_gera_alerta(client: TestClient, db: Session) -> None:
    """Ontem e anteontem dentro da meta; hoje so o cafe da manha (bem abaixo)."""
    _paciente_vinculado(db)
    _consumo(db, ONTEM - timedelta(days=1), "2000")
    _consumo(db, ONTEM, "2050")
    _consumo(db, HOJE, "300", hora=8)

    assert _processar(client)["alertas_gerados"] == 0
    assert db.query(AlertaDesvioPlano).count() == 0


def test_fechar_de_novo_nao_duplica(db: Session) -> None:
    _paciente_vinculado(db)
    _consumo(db, ONTEM - timedelta(days=1), "2700")
    _consumo(db, ONTEM, "2800")

    assert alertas_desvio.fechar_alertas_do_dia_anterior(db) == (ONTEM, 1)
    assert alertas_desvio.fechar_alertas_do_dia_anterior(db) == (ONTEM, 0)
    assert db.query(AlertaDesvioPlano).count() == 1


def test_script_fecha_ontem_ou_o_dia_informado(
    db: Session, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _paciente_vinculado(db)
    _consumo(db, ONTEM - timedelta(days=1), "2700")
    _consumo(db, ONTEM, "2800")
    monkeypatch.setattr(processar_alertas_desvio, "SessionLocal", lambda: nullcontext(db))

    processar_alertas_desvio.main([])
    processar_alertas_desvio.main(["--dia", HOJE.isoformat()])

    saida = capsys.readouterr().out
    assert f"Alertas de desvio de {ONTEM.isoformat()}: 1 gerados." in saida
    assert f"Alertas de desvio de {HOJE.isoformat()}: 0 gerados." in saida


def test_agendador_roda_os_dois_fechamentos_mesmo_se_um_falhar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chamadas = []

    def gamificacao() -> None:
        chamadas.append("gamificacao")
        raise RuntimeError("banco fora")

    monkeypatch.setattr(
        agendador,
        "FECHAMENTOS",
        {"gamificacao": gamificacao, "alertas de desvio": lambda: chamadas.append("alertas")},
    )

    agendador.executar()

    assert chamadas == ["gamificacao", "alertas"]


def test_agendador_fecha_alertas_de_verdade(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _paciente_vinculado(db)
    _consumo(db, ONTEM - timedelta(days=1), "2700")
    _consumo(db, ONTEM, "2800")
    monkeypatch.setattr(agendador, "SessionLocal", lambda: nullcontext(db))

    agendador.executar()

    assert db.query(AlertaDesvioPlano).filter_by(data_referencia=ONTEM).count() == 1
