"""Testes de alimentos personalizados e da busca unificada (RF22)."""

from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.alimento_taco import AlimentoTaco

ROTA_CADASTRO = "/api/v1/alimentos-personalizados"
ROTA_BUSCA = "/api/v1/alimentos"


def _payload(**sobrescrever: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "paciente_id": 1,
        "nome": "Pao de queijo da vovo",
        "kcal_100g": "320.50",
        "carbs_100g": "38.00",
        "prot_100g": "6.50",
        "gord_100g": "15.00",
    }
    payload.update(sobrescrever)
    return payload


def _cadastrar(client: TestClient, **kwargs: Any) -> dict[str, Any]:
    resposta = client.post(ROTA_CADASTRO, json=_payload(**kwargs))
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def _taco(db: Session, nome: str) -> None:
    db.add(
        AlimentoTaco(
            nome=nome,
            categoria="Cereais e derivados",
            kcal_100g=Decimal("100.00"),
            carbs_100g=Decimal("20.00"),
            prot_100g=Decimal("5.00"),
            gord_100g=Decimal("1.00"),
        )
    )
    db.commit()


class TestCadastro:
    def test_cadastra_alimento_com_valores_por_100g(self, client: TestClient) -> None:
        corpo = _cadastrar(client)

        assert corpo["id"] > 0
        assert corpo["paciente_id"] == 1
        assert corpo["nome"] == "Pao de queijo da vovo"
        assert corpo["kcal_100g"] == 320.5
        assert isinstance(corpo["kcal_100g"], float)

    def test_nome_sem_espacos_nas_pontas(self, client: TestClient) -> None:
        assert _cadastrar(client, nome="  Bolo de fuba  ")["nome"] == "Bolo de fuba"

    def test_recusa_nome_duplicado_do_mesmo_paciente(self, client: TestClient) -> None:
        _cadastrar(client, nome="Bolo de fuba")

        resposta = client.post(ROTA_CADASTRO, json=_payload(nome="BOLO DE FUBA"))

        assert resposta.status_code == 409

    def test_aceita_mesmo_nome_para_pacientes_diferentes(self, client: TestClient) -> None:
        _cadastrar(client, paciente_id=1, nome="Bolo de fuba")

        resposta = client.post(ROTA_CADASTRO, json=_payload(paciente_id=2, nome="Bolo de fuba"))

        assert resposta.status_code == 201

    def test_recusa_nome_vazio(self, client: TestClient) -> None:
        assert client.post(ROTA_CADASTRO, json=_payload(nome="   ")).status_code == 422

    def test_recusa_valor_negativo(self, client: TestClient) -> None:
        assert client.post(ROTA_CADASTRO, json=_payload(prot_100g="-1")).status_code == 422

    def test_recusa_macro_acima_de_100g(self, client: TestClient) -> None:
        assert client.post(ROTA_CADASTRO, json=_payload(carbs_100g="101")).status_code == 422

    def test_recusa_macros_que_somam_mais_de_100g(self, client: TestClient) -> None:
        payload = _payload(carbs_100g="60", prot_100g="30", gord_100g="20")

        assert client.post(ROTA_CADASTRO, json=payload).status_code == 422

    def test_recusa_kcal_acima_do_limite(self, client: TestClient) -> None:
        assert client.post(ROTA_CADASTRO, json=_payload(kcal_100g="901")).status_code == 422

    def test_recusa_campo_obrigatorio_ausente(self, client: TestClient) -> None:
        payload = _payload()
        del payload["kcal_100g"]

        assert client.post(ROTA_CADASTRO, json=payload).status_code == 422


class TestBuscaUnificada:
    def test_traz_taco_e_personalizados_do_paciente(self, client: TestClient, db: Session) -> None:
        _taco(db, "Pao, de queijo, assado")
        _cadastrar(client, nome="Pao de queijo da vovo")

        corpo = client.get(ROTA_BUSCA, params={"nome": "queijo", "paciente_id": 1}).json()

        assert {(i["origem"], i["nome"]) for i in corpo} == {
            ("personalizado", "Pao de queijo da vovo"),
            ("taco", "Pao, de queijo, assado"),
        }

    def test_item_personalizado_tem_mesmo_formato_do_taco(
        self, client: TestClient, db: Session
    ) -> None:
        _taco(db, "Bolo, de fuba")
        _cadastrar(client, nome="Bolo da tia")

        corpo = client.get(ROTA_BUSCA, params={"nome": "bolo", "paciente_id": 1}).json()

        assert len(corpo) == 2
        for item in corpo:
            assert set(item) == {
                "origem",
                "id",
                "nome",
                "categoria",
                "kcal_100g",
                "carbs_100g",
                "prot_100g",
                "gord_100g",
            }
            assert isinstance(item["kcal_100g"], float)
        personalizado = next(i for i in corpo if i["origem"] == "personalizado")
        assert personalizado["categoria"] == "Personalizado"
        assert personalizado["kcal_100g"] == 320.5

    def test_sem_paciente_busca_so_na_taco(self, client: TestClient, db: Session) -> None:
        _taco(db, "Bolo, de fuba")
        _cadastrar(client, nome="Bolo da tia")

        corpo = client.get(ROTA_BUSCA, params={"nome": "bolo"}).json()

        assert [i["origem"] for i in corpo] == ["taco"]

    def test_nao_mostra_alimento_de_outro_paciente(self, client: TestClient) -> None:
        _cadastrar(client, paciente_id=1, nome="Bolo da tia")

        corpo = client.get(ROTA_BUSCA, params={"nome": "bolo", "paciente_id": 2}).json()

        assert corpo == []

    def test_busca_case_insensitive_e_ordem_alfabetica(
        self, client: TestClient, db: Session
    ) -> None:
        _taco(db, "Bolo, simples")
        _cadastrar(client, nome="Bolo de cenoura")

        corpo = client.get(ROTA_BUSCA, params={"nome": "BOLO", "paciente_id": 1}).json()

        assert [i["nome"] for i in corpo] == ["Bolo de cenoura", "Bolo, simples"]

    def test_pagina_sobre_a_uniao_das_duas_fontes(self, client: TestClient, db: Session) -> None:
        _taco(db, "Bolo A")
        _taco(db, "Bolo C")
        _cadastrar(client, nome="Bolo B")
        _cadastrar(client, nome="Bolo D")

        def pagina(deslocamento: int) -> list[str]:
            resposta = client.get(
                ROTA_BUSCA,
                params={
                    "nome": "bolo",
                    "paciente_id": 1,
                    "limite": 2,
                    "deslocamento": deslocamento,
                },
            )
            return [i["nome"] for i in resposta.json()]

        assert pagina(0) == ["Bolo A", "Bolo B"]
        assert pagina(2) == ["Bolo C", "Bolo D"]

    def test_recusa_nome_vazio(self, client: TestClient) -> None:
        assert client.get(ROTA_BUSCA, params={"nome": ""}).status_code == 422

    def test_sem_resultado_retorna_lista_vazia(self, client: TestClient) -> None:
        resposta = client.get(ROTA_BUSCA, params={"nome": "inexistente", "paciente_id": 1})

        assert resposta.status_code == 200
        assert resposta.json() == []
