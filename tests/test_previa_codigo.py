"""Previa publica do nutricionista a partir do codigo (cadastro vinculado do prototipo)."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.vinculo import CodigoVinculacao
from tests import factories

NUTRI = 10


def _gerar(client: TestClient) -> str:
    resposta = client.post(
        "/api/v1/linking-code", headers=factories.headers_de(NUTRI, "nutricionista")
    )
    assert resposta.status_code in (200, 201), resposta.text
    return resposta.json()["codigo"]


def test_previa_mostra_nome_e_crn_sem_login(client: TestClient, db: Session) -> None:
    factories.criar_nutricionista(db, NUTRI, nome="Dra. Camila Mendes")
    codigo = _gerar(client)

    resposta = client.get(f"/api/v1/linking-code/{codigo}/previa")

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["nutricionista"]["nome"] == "Dra. Camila Mendes"
    assert corpo["nutricionista"]["id"] == NUTRI
    assert corpo["crn"] == "CRN-3 00010"
    assert "expira_em" in corpo


def test_previa_nao_resgata_o_codigo(client: TestClient, db: Session) -> None:
    factories.criar_nutricionista(db, NUTRI)
    factories.criar_paciente(db, 1)
    codigo = _gerar(client)

    client.get(f"/api/v1/linking-code/{codigo}/previa")
    resgate = client.post("/api/v1/link", json={"codigo": codigo}, headers=factories.headers_de(1))

    assert resgate.status_code in (200, 201), resgate.text
    # Depois de resgatado, o codigo nao mostra mais ninguem
    assert client.get(f"/api/v1/linking-code/{codigo}/previa").status_code == 404


def test_codigo_invalido_ou_expirado(client: TestClient, db: Session) -> None:
    factories.criar_nutricionista(db, NUTRI)
    codigo = _gerar(client)
    registro = db.query(CodigoVinculacao).one()
    registro.expira_em = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()

    assert client.get(f"/api/v1/linking-code/{codigo}/previa").status_code == 404
    assert client.get("/api/v1/linking-code/000000/previa").status_code in (404,)
    assert client.get("/api/v1/linking-code/12ab56/previa").status_code == 422
