"""Rascunho do plano alimentar e metas de carboidrato e gordura (prototipo do painel)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.vinculo import Vinculo
from tests import factories

NUTRI, OUTRO_NUTRI, PACIENTE = 10, 20, 11
BASE = f"/api/v1/pacientes/{PACIENTE}"
RASCUNHO = f"{BASE}/planos/rascunho"
NUTRI_H = factories.headers_de
PLANO: dict[str, Any] = {
    "titulo": "Hipertrofia",
    "refeicoes": [
        {
            "nome": "Almoco",
            "meta_kcal": 800,
            "meta_proteinas_g": 50,
            "meta_carboidratos_g": 90,
            "meta_gorduras_g": 25,
            "alimentos": [{"nome_alimento": "Arroz", "quantidade_g": 150}],
        },
        {
            "nome": "Jantar",
            "meta_kcal": 600,
            "meta_proteinas_g": 40,
            "meta_carboidratos_g": 60,
            "alimentos": [{"nome_alimento": "Frango", "quantidade_g": 120}],
        },
    ],
}


@pytest.fixture(autouse=True)
def _cenario(db: Session) -> None:
    factories.criar_nutricionista(db, NUTRI)
    factories.criar_nutricionista(db, OUTRO_NUTRI)
    factories.criar_paciente(db, PACIENTE)
    db.add(Vinculo(nutricionista_id=NUTRI, paciente_id=PACIENTE, status="ativo"))
    db.commit()


def _h(usuario_id: int = NUTRI) -> dict[str, str]:
    perfil = "paciente" if usuario_id == PACIENTE else "nutricionista"
    return factories.headers_de(usuario_id, perfil)


def test_rascunho_nao_vale_para_o_paciente_ate_publicar(client: TestClient) -> None:
    salvo = client.put(RASCUNHO, json=PLANO, headers=_h())
    assert salvo.status_code == 200, salvo.text
    assert salvo.json()["rascunho"] is True
    assert salvo.json()["ativo"] is False

    assert client.get(f"{BASE}/planos/ativo", headers=_h(PACIENTE)).status_code == 404
    assert client.get(f"{BASE}/planos/versoes", headers=_h()).json() == []
    assert client.get(f"{BASE}/perfil", headers=_h(PACIENTE)).json()["meta"]["kcal"] is None

    # Salvar de novo substitui o mesmo rascunho
    editado = client.put(RASCUNHO, json={**PLANO, "titulo": "Hipertrofia 2"}, headers=_h())
    assert editado.json()["id"] == salvo.json()["id"]
    assert client.get(RASCUNHO, headers=_h()).json()["titulo"] == "Hipertrofia 2"


def test_publicar_cria_versao_e_apaga_o_rascunho(client: TestClient) -> None:
    client.put(RASCUNHO, json=PLANO, headers=_h())

    publicado = client.post(f"{RASCUNHO}/publicar", headers=_h())

    assert publicado.status_code == 201, publicado.text
    plano = publicado.json()
    assert (plano["versao"], plano["ativo"], plano["rascunho"]) == (1, True, False)
    assert plano["totais"] == {
        "meta_kcal": 1400.0,
        "meta_proteinas_g": 90.0,
        "meta_carboidratos_g": 150.0,
        "meta_gorduras_g": 25.0,
    }
    assert client.get(RASCUNHO, headers=_h()).status_code == 404
    meta = client.get(f"{BASE}/perfil", headers=_h(PACIENTE)).json()["meta"]
    assert meta["origem"] == "plano"
    assert (meta["kcal"], meta["carboidratos_g"], meta["gorduras_g"]) == (1400, 150, 25)


def test_descartar_rascunho(client: TestClient) -> None:
    client.put(RASCUNHO, json=PLANO, headers=_h())

    assert client.delete(RASCUNHO, headers=_h()).status_code == 204
    assert client.get(RASCUNHO, headers=_h()).status_code == 404
    assert client.post(f"{RASCUNHO}/publicar", headers=_h()).status_code == 404


def test_rascunho_so_do_nutricionista_vinculado(client: TestClient) -> None:
    assert client.put(RASCUNHO, json=PLANO, headers=_h(OUTRO_NUTRI)).status_code == 403
    assert client.get(RASCUNHO, headers=_h(PACIENTE)).status_code == 403
    assert client.get(RASCUNHO).status_code == 401
