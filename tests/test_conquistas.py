from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conquista import ConquistaPaciente
from app.models.refeicao import Refeicao
from app.services.gamificacao import processar_gamificacao_diaria
from tests import factories
from tests.test_gamificacao import DIA, _paciente, _refeicao

URL = "/api/v1/gamificacao/conquistas"


def test_fechamento_concede_marco_de_ofensiva(client: TestClient, db: Session) -> None:
    paciente = _paciente(db)
    paciente.streak = 29
    db.commit()
    _refeicao(db, paciente.id, 8, "100")
    _refeicao(db, paciente.id, 12, "100")
    headers = factories.headers_de(paciente.id)
    antes = client.get(URL, headers=headers)
    assert antes.status_code == 200
    assert antes.json()[0]["progresso"] == 29
    assert antes.json()[0]["obtida_em"] is None

    assert processar_gamificacao_diaria(db, DIA) == 1
    assert processar_gamificacao_diaria(db, DIA) == 0
    obtida = client.get(URL, headers=headers).json()[0]
    assert obtida["codigo"] == "streak_30"
    assert obtida["progresso"] == 30
    assert obtida["obtida_em"] is not None

    processar_gamificacao_diaria(db, date(2026, 10, 13))
    assert paciente.streak == 0
    assert client.get(URL, headers=headers).json()[0] == obtida
    assert len(db.scalars(select(ConquistaPaciente)).all()) == 1


def test_catalogo_isola_conquistas_e_conta_refeicoes(client: TestClient, db: Session) -> None:
    paciente = _paciente(db)
    outro = _paciente(db, paciente_id=2)
    paciente.streak = 30
    _refeicao(db, paciente.id, 8, "100", dia=date(2026, 10, 11))
    refeicao = db.scalar(select(Refeicao).where(Refeicao.paciente_id == paciente.id))
    db.add_all(
        Refeicao(paciente_id=paciente.id, consumida_em=refeicao.consumida_em, tipo=refeicao.tipo)
        for _ in range(99)
    )
    db.commit()

    headers = factories.headers_de(paciente.id)
    assert client.get(URL, headers=headers).json()[1]["obtida_em"] is None
    processar_gamificacao_diaria(db, DIA)

    assert paciente.streak == 0
    conquistas = client.get(URL, headers=headers).json()
    assert {item["codigo"] for item in conquistas if item["obtida_em"]} == {
        "streak_30",
        "refeicoes_100",
    }
    assert all(
        item["obtida_em"] is None and item["progresso"] == 0
        for item in client.get(URL, headers=factories.headers_de(outro.id)).json()
    )


def test_catalogo_exige_paciente_autenticado(client: TestClient, db: Session) -> None:
    nutri = factories.criar_nutricionista(db, 3)
    assert client.get(URL).status_code == 401
    assert (
        client.get(URL, headers=factories.headers_de(nutri.id, "nutricionista")).status_code == 403
    )
