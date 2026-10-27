"""Testes do modulo social e amizades (RF05)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.paciente import Paciente


@pytest.fixture
def paciente_a(db: Session) -> Paciente:
    p = Paciente(id=1, username="atleta_joao", streak=5, xp=150)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@pytest.fixture
def paciente_b(db: Session) -> Paciente:
    p = Paciente(id=2, username="maria_fit", streak=10, xp=300)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@pytest.fixture
def paciente_c(db: Session) -> Paciente:
    p = Paciente(id=3, username="carlos_runner", streak=2, xp=50)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


class TestSolicitacaoAmizade:
    def test_envia_solicitacao_com_sucesso(
        self, client: TestClient, paciente_a: Paciente, paciente_b: Paciente
    ) -> None:
        resposta = client.post(
            "/api/v1/amizades",
            json={"paciente_id": paciente_a.id, "amigo_id": paciente_b.id},
        )
        assert resposta.status_code == 201
        dados = resposta.json()
        assert dados["pac_id"] == paciente_a.id
        assert dados["amigo_id"] == paciente_b.id
        assert dados["status"] == "pendente"

    def test_impede_auto_amizade(self, client: TestClient, paciente_a: Paciente) -> None:
        resposta = client.post(
            "/api/v1/amizades",
            json={"paciente_id": paciente_a.id, "amigo_id": paciente_a.id},
        )
        assert resposta.status_code == 422
        assert "mesmo" in resposta.json()["detail"].lower()

    def test_paciente_ou_amigo_inexistente_retorna_404(
        self, client: TestClient, paciente_a: Paciente
    ) -> None:
        resposta = client.post(
            "/api/v1/amizades",
            json={"paciente_id": paciente_a.id, "amigo_id": 9999},
        )
        assert resposta.status_code == 404

    def test_impede_solicitacao_duplicada_pendente(
        self, client: TestClient, paciente_a: Paciente, paciente_b: Paciente
    ) -> None:
        client.post(
            "/api/v1/amizades",
            json={"paciente_id": paciente_a.id, "amigo_id": paciente_b.id},
        )
        resposta = client.post(
            "/api/v1/amizades",
            json={"paciente_id": paciente_a.id, "amigo_id": paciente_b.id},
        )
        assert resposta.status_code == 409
        assert "pendente" in resposta.json()["detail"].lower()

    def test_convite_cruzado_aceita_automaticamente(
        self, client: TestClient, paciente_a: Paciente, paciente_b: Paciente
    ) -> None:
        # A envia para B
        client.post(
            "/api/v1/amizades",
            json={"paciente_id": paciente_a.id, "amigo_id": paciente_b.id},
        )
        # B também envia para A (convite cruzado)
        resposta = client.post(
            "/api/v1/amizades",
            json={"paciente_id": paciente_b.id, "amigo_id": paciente_a.id},
        )
        assert resposta.status_code == 201
        assert resposta.json()["status"] == "aceito"


class TestRespostaSolicitacao:
    def test_aceita_solicitacao(
        self, client: TestClient, paciente_a: Paciente, paciente_b: Paciente
    ) -> None:
        post_resp = client.post(
            "/api/v1/amizades",
            json={"paciente_id": paciente_a.id, "amigo_id": paciente_b.id},
        )
        amizade_id = post_resp.json()["id"]

        resp = client.put(
            f"/api/v1/amizades/{amizade_id}/responder",
            json={"paciente_id": paciente_b.id, "aceitar": True},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "aceito"

    def test_recusa_solicitacao(
        self, client: TestClient, paciente_a: Paciente, paciente_b: Paciente
    ) -> None:
        post_resp = client.post(
            "/api/v1/amizades",
            json={"paciente_id": paciente_a.id, "amigo_id": paciente_b.id},
        )
        amizade_id = post_resp.json()["id"]

        resp = client.put(
            f"/api/v1/amizades/{amizade_id}/responder",
            json={"paciente_id": paciente_b.id, "aceitar": False},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "recusado"

    def test_terceiro_nao_pode_responder(
        self,
        client: TestClient,
        paciente_a: Paciente,
        paciente_b: Paciente,
        paciente_c: Paciente,
    ) -> None:
        post_resp = client.post(
            "/api/v1/amizades",
            json={"paciente_id": paciente_a.id, "amigo_id": paciente_b.id},
        )
        amizade_id = post_resp.json()["id"]

        resp = client.put(
            f"/api/v1/amizades/{amizade_id}/responder",
            json={"paciente_id": paciente_c.id, "aceitar": True},
        )
        assert resp.status_code == 403


class TestListagemAmizades:
    def test_lista_amizades_e_filtra_por_status(
        self,
        client: TestClient,
        paciente_a: Paciente,
        paciente_b: Paciente,
        paciente_c: Paciente,
    ) -> None:
        # A envia para B e B aceita
        r1 = client.post(
            "/api/v1/amizades",
            json={"paciente_id": paciente_a.id, "amigo_id": paciente_b.id},
        )
        client.put(
            f"/api/v1/amizades/{r1.json()['id']}/responder",
            json={"paciente_id": paciente_b.id, "aceitar": True},
        )

        # C envia para A (fica pendente)
        client.post(
            "/api/v1/amizades",
            json={"paciente_id": paciente_c.id, "amigo_id": paciente_a.id},
        )

        # Lista todas as amizades de A
        resp = client.get(f"/api/v1/amizades?paciente_id={paciente_a.id}")
        assert resp.status_code == 200
        itens = resp.json()
        assert len(itens) == 2

        # Filtra apenas por aceitas
        resp_aceitos = client.get(f"/api/v1/amizades?paciente_id={paciente_a.id}&status=aceito")
        assert resp_aceitos.status_code == 200
        itens_aceitos = resp_aceitos.json()
        assert len(itens_aceitos) == 1
        assert itens_aceitos[0]["paciente_id"] == paciente_b.id
        assert itens_aceitos[0]["username"] == "maria_fit"


class TestRemoverAmizade:
    def test_remove_amizade_com_sucesso(
        self, client: TestClient, paciente_a: Paciente, paciente_b: Paciente
    ) -> None:
        r = client.post(
            "/api/v1/amizades",
            json={"paciente_id": paciente_a.id, "amigo_id": paciente_b.id},
        )
        amizade_id = r.json()["id"]

        del_resp = client.delete(f"/api/v1/amizades/{amizade_id}?paciente_id={paciente_a.id}")
        assert del_resp.status_code == 204

        # Confirmar exclusao
        lista = client.get(f"/api/v1/amizades?paciente_id={paciente_a.id}").json()
        assert len(lista) == 0

    def test_usuario_estranho_nao_pode_remover(
        self,
        client: TestClient,
        paciente_a: Paciente,
        paciente_b: Paciente,
        paciente_c: Paciente,
    ) -> None:
        r = client.post(
            "/api/v1/amizades",
            json={"paciente_id": paciente_a.id, "amigo_id": paciente_b.id},
        )
        amizade_id = r.json()["id"]

        del_resp = client.delete(f"/api/v1/amizades/{amizade_id}?paciente_id={paciente_c.id}")
        assert del_resp.status_code == 403
