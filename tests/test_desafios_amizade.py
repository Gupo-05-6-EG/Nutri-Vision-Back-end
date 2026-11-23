"""Desafio so com amigos aceitos: criar, convidar depois, aceitar e placar (BE-18)."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import criar_token_acesso
from app.models.amizade import Amizade, StatusAmizade
from tests import factories

ROTA = "/api/v1/challenges"
CORPO = {
    "nome": "Semana equilibrada",
    "tipo": "refeicoes",
    "regra": "Registrar as 4 refeicoes",
    "inicio_em": "2026-10-12T00:00:00-03:00",
    "fim_em": "2026-10-19T00:00:00-03:00",
}


def _h(usuario_id: int) -> dict[str, str]:
    token, _ = criar_token_acesso(usuario_id, "paciente")
    return {"Authorization": f"Bearer {token}"}


def _pacientes(db: Session, *ids: int) -> None:
    for paciente_id in ids:
        factories.criar_paciente(db, paciente_id)


def _amizade(db: Session, a: int, b: int, status: StatusAmizade = StatusAmizade.ACEITO) -> None:
    db.add(Amizade(pac_id=a, amigo_id=b, status=status))
    db.commit()


def test_amigo_aceito_entra_no_desafio_e_no_placar(client: TestClient, db: Session) -> None:
    _pacientes(db, 1, 2)
    _amizade(db, 2, 1)  # quem pediu a amizade foi o outro: vale nos dois sentidos

    criado = client.post(ROTA, headers=_h(1), json={**CORPO, "convidados": [2]})
    assert criado.status_code == 201, criado.text
    desafio_id = criado.json()["id"]
    aceite = client.post(f"{ROTA}/{desafio_id}/response", headers=_h(2), json={"aceitar": True})
    assert aceite.status_code == 200, aceite.text

    placar = client.get(f"{ROTA}/{desafio_id}/leaderboard", headers=_h(2))
    assert placar.status_code == 200
    assert {p["paciente_id"] for p in placar.json()["participantes"]} == {1, 2}


def test_nao_convida_quem_nao_e_amigo(client: TestClient, db: Session) -> None:
    _pacientes(db, 1, 2)

    resposta = client.post(ROTA, headers=_h(1), json={**CORPO, "convidados": [2]})

    assert resposta.status_code == 409


def test_amizade_pendente_ainda_nao_permite_convite(client: TestClient, db: Session) -> None:
    _pacientes(db, 1, 2)
    _amizade(db, 1, 2, StatusAmizade.PENDENTE)

    resposta = client.post(ROTA, headers=_h(1), json={**CORPO, "convidados": [2]})

    assert resposta.status_code == 409


def test_convite_depois_de_criar_tambem_exige_amizade(client: TestClient, db: Session) -> None:
    _pacientes(db, 1, 2, 3)
    _amizade(db, 1, 2)
    desafio_id = client.post(ROTA, headers=_h(1), json={**CORPO, "convidados": []}).json()["id"]

    amigo = client.post(f"{ROTA}/{desafio_id}/invites", headers=_h(1), json={"pacientes": [2]})
    estranho = client.post(f"{ROTA}/{desafio_id}/invites", headers=_h(1), json={"pacientes": [3]})

    assert amigo.status_code == 201, amigo.text
    assert estranho.status_code == 409
