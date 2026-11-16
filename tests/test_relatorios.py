from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.vinculo import Vinculo
from tests import factories

URL = "/api/v1/pacientes/1/relatorio.pdf"
PERIODO = {"inicio": "2026-11-07", "fim": "2026-11-07"}


def test_pdf_restrito_ao_nutricionista_vinculado(client: TestClient, db: Session) -> None:
    factories.criar_paciente(db, 1)
    factories.criar_nutricionista(db, 10)
    factories.criar_nutricionista(db, 11)
    db.add(Vinculo(nutricionista_id=10, paciente_id=1))
    db.commit()
    assert client.get(URL, params=PERIODO).status_code == 401
    assert client.get(URL, params=PERIODO, headers=factories.headers_de(1)).status_code == 403
    outro = factories.headers_de(11, "nutricionista")
    assert client.get(URL, params=PERIODO, headers=outro).status_code == 403

    headers = factories.headers_de(10, "nutricionista")
    resposta = client.get(URL, params=PERIODO, headers=headers)
    assert resposta.status_code == 200
    assert resposta.content.startswith(b"%PDF-")
    assert resposta.headers["content-type"] == "application/pdf"
    assert resposta.headers["cache-control"] == "no-store"
    assert resposta.headers["content-disposition"] == 'attachment; filename="evolucao-1.pdf"'


def test_relatorio_com_consumo_e_meta(client: TestClient, db: Session) -> None:
    paciente = factories.criar_paciente(db, 1)
    factories.criar_nutricionista(db, 10)
    paciente.meta_kcal = 2000
    db.add(Vinculo(nutricionista_id=10, paciente_id=1))
    db.commit()
    dados = factories.refeicao(paciente_id=1, consumida_em=datetime(2026, 11, 7, 15, tzinfo=UTC))
    assert (
        client.post("/api/v1/refeicoes", json=dados, headers=factories.headers_de(1)).status_code
        == 201
    )

    headers = factories.headers_de(10, "nutricionista")
    resposta = client.get(URL, params=PERIODO, headers=headers)
    assert resposta.status_code == 200
    assert resposta.content.startswith(b"%PDF-")
    for fim in ("2026-11-06", "2027-02-05", "9999-12-31"):
        assert client.get(URL, params={**PERIODO, "fim": fim}, headers=headers).status_code == 422
