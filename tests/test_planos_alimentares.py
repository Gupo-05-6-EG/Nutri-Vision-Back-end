"""Testes do plano alimentar (RF09.1)."""

from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import criar_token_acesso
from app.models.alimento_taco import AlimentoTaco
from app.models.vinculo import Vinculo
from tests import factories

# 10 e nutricionista vinculado ao paciente 11; 20 e outro nutricionista, sem
# vinculo; 12 e outro paciente.
NUTRI, OUTRO_NUTRI, PACIENTE, OUTRO_PACIENTE = 10, 20, 11, 12


def _rota(paciente_id: int = PACIENTE) -> str:
    return f"/api/v1/pacientes/{paciente_id}/planos"


def _headers(usuario_id: int, perfil: str) -> dict[str, str]:
    token, _ = criar_token_acesso(usuario_id, perfil)
    return {"Authorization": f"Bearer {token}"}


NUTRI_HEADERS = _headers(NUTRI, "nutricionista")


@pytest.fixture(autouse=True)
def _usuarios(db: Session) -> None:
    factories.criar_nutricionista(db, NUTRI)
    factories.criar_nutricionista(db, OUTRO_NUTRI)
    factories.criar_paciente(db, PACIENTE)
    factories.criar_paciente(db, OUTRO_PACIENTE)
    db.add(Vinculo(nutricionista_id=NUTRI, paciente_id=PACIENTE))
    db.commit()


def _plano(**extra: Any) -> dict[str, Any]:
    return {
        "titulo": "Reeducacao alimentar",
        "observacao": "Beber 2L de agua por dia",
        "refeicoes": [
            {
                "nome": "Cafe da manha",
                "horario": "07:30",
                "meta_kcal": 400,
                "meta_proteinas_g": 20,
                "alimentos": [
                    {"nome_alimento": "Pao integral", "quantidade_g": 50},
                    {"nome_alimento": "Ovo cozido", "quantidade_g": 100},
                ],
            },
            {
                "nome": "Ceia",
                "meta_kcal": 150.5,
                "meta_proteinas_g": 10,
                "observacao": "Opcional",
                "alimentos": [{"nome_alimento": "Iogurte natural", "quantidade_g": 170}],
            },
        ],
        **extra,
    }


def _prescrever(client: TestClient, **extra: Any) -> dict[str, Any]:
    resposta = client.post(_rota(), json=_plano(**extra), headers=NUTRI_HEADERS)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


class TestPrescricao:
    def test_cria_plano_com_blocos_na_ordem_e_metas_somadas(self, client: TestClient) -> None:
        corpo = _prescrever(client)

        assert corpo["paciente_id"] == PACIENTE
        assert corpo["nutricionista_id"] == NUTRI
        assert corpo["ativo"] is True
        assert [r["nome"] for r in corpo["refeicoes"]] == ["Cafe da manha", "Ceia"]
        cafe = corpo["refeicoes"][0]
        assert cafe["horario"] == "07:30:00"
        assert [a["nome_alimento"] for a in cafe["alimentos"]] == ["Pao integral", "Ovo cozido"]
        assert corpo["totais"] == {"meta_kcal": 550.5, "meta_proteinas_g": 30.0}
        assert corpo["criado_em"].endswith(("Z", "+00:00"))

    def test_novo_plano_desativa_o_anterior(self, client: TestClient) -> None:
        primeiro = _prescrever(client, titulo="Plano 1")
        segundo = _prescrever(client, titulo="Plano 2")

        ativo = client.get(f"{_rota()}/ativo", headers=NUTRI_HEADERS).json()

        assert ativo["id"] == segundo["id"] != primeiro["id"]
        assert ativo["titulo"] == "Plano 2"

    def test_aceita_alimento_da_taco(self, client: TestClient, db: Session) -> None:
        taco = AlimentoTaco(
            nome="Arroz, integral, cozido",
            categoria="Cereais",
            kcal_100g=Decimal("124"),
            carbs_100g=Decimal("25.8"),
            prot_100g=Decimal("2.6"),
            gord_100g=Decimal("1"),
        )
        db.add(taco)
        db.commit()
        plano = _plano()
        plano["refeicoes"][0]["alimentos"][0]["alimento_taco_id"] = taco.id

        resposta = client.post(_rota(), json=plano, headers=NUTRI_HEADERS)

        assert resposta.status_code == 201, resposta.text
        assert resposta.json()["refeicoes"][0]["alimentos"][0]["alimento_taco_id"] == taco.id

    def test_recusa_alimento_taco_inexistente(self, client: TestClient) -> None:
        plano = _plano()
        plano["refeicoes"][0]["alimentos"][0]["alimento_taco_id"] = 999

        resposta = client.post(_rota(), json=plano, headers=NUTRI_HEADERS)

        assert resposta.status_code == 422

    @pytest.mark.parametrize(
        "ajuste",
        [
            lambda p: p.update(refeicoes=[]),
            lambda p: p.update(titulo="   "),
            lambda p: p["refeicoes"][0].update(alimentos=[]),
            lambda p: p["refeicoes"][0].update(meta_kcal=-1),
            lambda p: p["refeicoes"][0].update(nome=""),
            lambda p: p["refeicoes"][0]["alimentos"][0].update(quantidade_g=0),
        ],
        ids=[
            "sem-refeicoes",
            "titulo-vazio",
            "bloco-sem-alimentos",
            "meta-negativa",
            "nome-vazio",
            "quantidade-zero",
        ],
    )
    def test_recusa_dados_invalidos(self, client: TestClient, ajuste) -> None:
        plano = _plano()
        ajuste(plano)

        resposta = client.post(_rota(), json=plano, headers=NUTRI_HEADERS)

        assert resposta.status_code == 422


class TestAcesso:
    def test_sem_token_retorna_401(self, client: TestClient) -> None:
        assert client.post(_rota(), json=_plano()).status_code == 401

    def test_paciente_nao_prescreve(self, client: TestClient) -> None:
        resposta = client.post(_rota(), json=_plano(), headers=_headers(PACIENTE, "paciente"))
        assert resposta.status_code == 403

    def test_nutricionista_sem_vinculo_nao_prescreve(self, client: TestClient) -> None:
        resposta = client.post(
            _rota(), json=_plano(), headers=_headers(OUTRO_NUTRI, "nutricionista")
        )
        assert resposta.status_code == 403

    def test_paciente_inexistente_retorna_404(self, client: TestClient) -> None:
        resposta = client.post(_rota(999), json=_plano(), headers=NUTRI_HEADERS)
        assert resposta.status_code == 404

    def test_paciente_le_o_proprio_plano(self, client: TestClient) -> None:
        _prescrever(client)

        resposta = client.get(f"{_rota()}/ativo", headers=_headers(PACIENTE, "paciente"))

        assert resposta.status_code == 200
        assert resposta.json()["titulo"] == "Reeducacao alimentar"

    def test_paciente_nao_le_plano_de_outro(self, client: TestClient) -> None:
        _prescrever(client)

        resposta = client.get(f"{_rota()}/ativo", headers=_headers(OUTRO_PACIENTE, "paciente"))

        assert resposta.status_code == 403

    def test_nutricionista_sem_vinculo_nao_le(self, client: TestClient) -> None:
        _prescrever(client)

        resposta = client.get(f"{_rota()}/ativo", headers=_headers(OUTRO_NUTRI, "nutricionista"))

        assert resposta.status_code == 403

    def test_sem_plano_ativo_retorna_404(self, client: TestClient) -> None:
        resposta = client.get(f"{_rota()}/ativo", headers=NUTRI_HEADERS)

        assert resposta.status_code == 404
        assert resposta.json()["detail"] == "Paciente sem plano ativo"
