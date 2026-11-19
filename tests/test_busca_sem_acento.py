"""Busca de alimentos e pacientes sem depender de acento nem de maiusculas (B4)."""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.texto import sem_acento
from app.models.alimento_personalizado import AlimentoPersonalizado
from app.models.alimento_taco import AlimentoTaco
from app.models.usuario import Usuario
from app.models.vinculo import Vinculo
from tests import factories


def _taco(nome: str) -> AlimentoTaco:
    return AlimentoTaco(
        nome=nome,
        categoria="Teste",
        kcal_100g=Decimal("100"),
        carbs_100g=Decimal("10"),
        prot_100g=Decimal("5"),
        gord_100g=Decimal("1"),
    )


@pytest.fixture(autouse=True)
def _dados(db: Session) -> None:
    factories.criar_paciente(db, 1)
    db.add_all([_taco("Feijão, preto, cozido"), _taco("Pão, de queijo"), _taco("Maçã, Fuji")])
    db.add(
        AlimentoPersonalizado(
            paciente_id=1,
            nome="Pão de açúcar da vó",
            kcal_100g=Decimal("300"),
            carbs_100g=Decimal("60"),
            prot_100g=Decimal("4"),
            gord_100g=Decimal("3"),
        )
    )
    db.commit()


def test_sem_acento() -> None:
    assert sem_acento("  Feijão   PRETO ") == "feijao preto"
    assert sem_acento("Maçã") == "maca"
    assert sem_acento(None) == ""


@pytest.mark.parametrize("termo", ["feijao", "FEIJÃO", "feijão preto", "Feijao, Preto"])
def test_busca_taco_ignora_acento(client: TestClient, termo: str) -> None:
    resposta = client.get(
        "/api/v1/alimentos-taco", params={"nome": termo}, headers=factories.headers_de(1)
    )

    assert resposta.status_code == 200
    assert [a["nome"] for a in resposta.json()] == ["Feijão, preto, cozido"]


def test_busca_unificada_ignora_acento(client: TestClient) -> None:
    resposta = client.get(
        "/api/v1/alimentos",
        params={"nome": "pao", "paciente_id": 1},
        headers=factories.headers_de(1),
    )

    assert {a["nome"] for a in resposta.json()} == {"Pão, de queijo", "Pão de açúcar da vó"}


def test_curinga_do_like_nao_vaza(client: TestClient) -> None:
    resposta = client.get(
        "/api/v1/alimentos-taco", params={"nome": "%"}, headers=factories.headers_de(1)
    )

    assert resposta.json() == []


def test_busca_de_paciente_do_nutricionista_ignora_acento(client: TestClient, db: Session) -> None:
    factories.criar_nutricionista(db, 10)
    factories.criar_paciente(db, 2)
    db.get(Usuario, 2).nome = "Joana Conceição"
    db.add(Vinculo(nutricionista_id=10, paciente_id=2, status="ativo"))
    db.commit()

    resposta = client.get(
        "/api/v1/patients",
        params={"busca": "conceicao"},
        headers=factories.headers_de(10, "nutricionista"),
    )

    assert [p["nome"] for p in resposta.json()] == ["Joana Conceição"]
