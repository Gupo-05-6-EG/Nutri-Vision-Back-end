"""Incentivo +10 XP do nutricionista vinculado (uma vez por dia)."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.historico_xp import HistoricoXP
from app.models.vinculo import Vinculo
from app.services.gamificacao import XP_INCENTIVO
from tests import factories

PACIENTE, NUTRI, OUTRO_NUTRI = 1, 10, 11
URL = f"/api/v1/pacientes/{PACIENTE}/incentivo"


def _cenario(db: Session, status_vinculo: str = "ativo") -> None:
    factories.criar_paciente(db, PACIENTE)
    factories.criar_nutricionista(db, NUTRI)
    factories.criar_nutricionista(db, OUTRO_NUTRI)
    db.add(Vinculo(nutricionista_id=NUTRI, paciente_id=PACIENTE, status=status_vinculo))
    db.commit()


def test_nutricionista_vinculado_da_incentivo_uma_vez_por_dia(
    client: TestClient, db: Session
) -> None:
    _cenario(db)
    headers = factories.headers_de(NUTRI, "nutricionista")

    primeira = client.post(URL, headers=headers)
    assert primeira.status_code == 201
    assert primeira.json() == {
        "paciente_id": PACIENTE,
        "xp_concedido": XP_INCENTIVO,
        "xp_total": XP_INCENTIVO,
    }
    assert client.post(URL, headers=headers).status_code == 409
    assert db.query(HistoricoXP).filter_by(paciente_id=PACIENTE).count() == 1


def test_sem_vinculo_ativo_ou_paciente_nao_pode(client: TestClient, db: Session) -> None:
    _cenario(db, status_vinculo="pendente")

    assert client.post(URL, headers=factories.headers_de(NUTRI, "nutricionista")).status_code == 403
    assert (
        client.post(URL, headers=factories.headers_de(OUTRO_NUTRI, "nutricionista")).status_code
        == 403
    )
    assert client.post(URL, headers=factories.headers_de(PACIENTE)).status_code == 403
    assert client.post(URL).status_code == 401
