"""Versionamento do plano alimentar e historico de versoes (Task 5.3, RF08).

Cenario: 10 e o nutricionista vinculado ao paciente 11; 20 e outro nutricionista,
sem vinculo (vira vinculado ao paciente 11 so nos testes que precisam); 12 e
outro paciente.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.plano_alimentar import PlanoAlimentar
from app.models.usuario import Usuario
from app.models.vinculo import Vinculo
from tests import factories

NUTRI, OUTRO_NUTRI, PACIENTE, OUTRO_PACIENTE = 10, 20, 11, 12
API = "/api/v1/pacientes"

NUTRI_HEADERS = factories.headers_de(NUTRI, "nutricionista")
OUTRO_NUTRI_HEADERS = factories.headers_de(OUTRO_NUTRI, "nutricionista")


@pytest.fixture(autouse=True)
def _usuarios(db: Session) -> None:
    factories.criar_nutricionista(db, NUTRI, nome="Dra. Ana")
    factories.criar_nutricionista(db, OUTRO_NUTRI, nome="Dr. Bruno")
    factories.criar_paciente(db, PACIENTE)
    factories.criar_paciente(db, OUTRO_PACIENTE)
    db.add(Vinculo(status="ativo", nutricionista_id=NUTRI, paciente_id=PACIENTE))
    db.commit()


def _plano(titulo: str = "Plano", **bloco: Any) -> dict[str, Any]:
    refeicao = {
        "nome": "Almoco",
        "horario": "12:00",
        "meta_kcal": 600,
        "meta_proteinas_g": 40,
        "alimentos": [{"nome_alimento": "Arroz", "quantidade_g": 150}],
        **bloco,
    }
    return {"titulo": titulo, "refeicoes": [refeicao]}


def _salvar(
    client: TestClient,
    plano: dict[str, Any],
    paciente_id: int = PACIENTE,
    headers: dict[str, str] = NUTRI_HEADERS,
) -> dict[str, Any]:
    resposta = client.post(f"{API}/{paciente_id}/planos", json=plano, headers=headers)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def _historico(
    client: TestClient, paciente_id: int = PACIENTE, headers: dict[str, str] = NUTRI_HEADERS
) -> list[dict[str, Any]]:
    resposta = client.get(f"{API}/{paciente_id}/planos/versoes", headers=headers)
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


class TestNumeracao:
    def test_primeiro_plano_e_a_versao_1(self, client: TestClient) -> None:
        assert _salvar(client, _plano())["versao"] == 1

    def test_cada_edicao_gera_a_versao_seguinte(self, client: TestClient) -> None:
        versoes = [_salvar(client, _plano(f"Plano {n}"))["versao"] for n in range(1, 4)]

        assert versoes == [1, 2, 3]

    def test_a_numeracao_e_por_paciente(self, client: TestClient, db: Session) -> None:
        db.add(Vinculo(status="ativo", nutricionista_id=NUTRI, paciente_id=OUTRO_PACIENTE))
        db.commit()

        _salvar(client, _plano("A1"), PACIENTE)
        _salvar(client, _plano("A2"), PACIENTE)

        assert _salvar(client, _plano("B1"), OUTRO_PACIENTE)["versao"] == 1

    def test_so_a_versao_mais_nova_fica_ativa(self, client: TestClient) -> None:
        for n in range(3):
            _salvar(client, _plano(f"Plano {n}"))

        ativo = client.get(f"{API}/{PACIENTE}/planos/ativo", headers=NUTRI_HEADERS).json()

        assert ativo["versao"] == 3
        assert [v["ativo"] for v in _historico(client)] == [True, False, False]

    def test_plano_recusado_nao_consome_numero_de_versao(self, client: TestClient) -> None:
        _salvar(client, _plano("Plano 1"))
        invalido = _plano("Plano 2")
        invalido["refeicoes"][0]["alimentos"][0]["alimento_taco_id"] = 999999

        recusado = client.post(f"{API}/{PACIENTE}/planos", json=invalido, headers=NUTRI_HEADERS)

        assert recusado.status_code == 422
        assert _salvar(client, _plano("Plano 2"))["versao"] == 2
        assert len(_historico(client)) == 2

    def test_banco_barra_versao_repetida_para_o_mesmo_paciente(self, db: Session) -> None:
        db.add(PlanoAlimentar(paciente_id=PACIENTE, versao=1, titulo="Primeiro"))
        db.flush()

        # begin_nested: o erro desfaz so este trecho, sem derrubar a sessao do teste.
        with pytest.raises(IntegrityError), db.begin_nested():
            db.add(PlanoAlimentar(paciente_id=PACIENTE, versao=1, titulo="Repetido"))


class TestHistorico:
    def test_lista_da_versao_mais_nova_para_a_mais_antiga(self, client: TestClient) -> None:
        _salvar(client, _plano("Primeiro"))
        _salvar(client, _plano("Segundo"))
        _salvar(client, _plano("Terceiro"))

        historico = _historico(client)

        assert [(v["versao"], v["titulo"]) for v in historico] == [
            (3, "Terceiro"),
            (2, "Segundo"),
            (1, "Primeiro"),
        ]

    def test_cada_versao_traz_o_plano_completo_como_foi_salvo(self, client: TestClient) -> None:
        _salvar(client, _plano("Antigo", meta_kcal=500))
        _salvar(client, _plano("Novo", meta_kcal=700))

        nova, antiga = _historico(client)

        assert antiga["refeicoes"][0]["meta_kcal"] == 500.0
        assert antiga["totais"] == {"meta_kcal": 500.0, "meta_proteinas_g": 40.0}
        assert nova["refeicoes"][0]["meta_kcal"] == 700.0
        assert nova["refeicoes"][0]["alimentos"][0]["nome_alimento"] == "Arroz"
        assert antiga["criado_em"].endswith(("Z", "+00:00"))

    def test_editar_nao_altera_as_versoes_antigas(self, client: TestClient) -> None:
        primeira = _salvar(client, _plano("Original"))
        _salvar(client, _plano("Editado", meta_kcal=900))

        antiga = _historico(client)[-1]

        assert antiga["id"] == primeira["id"]
        assert antiga["titulo"] == "Original"
        assert antiga["refeicoes"][0]["meta_kcal"] == 600.0

    def test_sem_plano_devolve_lista_vazia(self, client: TestClient) -> None:
        assert _historico(client) == []

    def test_nao_mistura_versoes_de_outro_paciente(self, client: TestClient, db: Session) -> None:
        db.add(Vinculo(status="ativo", nutricionista_id=NUTRI, paciente_id=OUTRO_PACIENTE))
        db.commit()
        _salvar(client, _plano("Do Joao"), PACIENTE)
        _salvar(client, _plano("Da Maria"), OUTRO_PACIENTE)

        assert [v["titulo"] for v in _historico(client, OUTRO_PACIENTE)] == ["Da Maria"]


class TestAutor:
    def test_cada_versao_traz_quem_a_salvou(self, client: TestClient, db: Session) -> None:
        db.add(Vinculo(status="ativo", nutricionista_id=OUTRO_NUTRI, paciente_id=PACIENTE))
        db.commit()
        _salvar(client, _plano("Da Ana"), headers=NUTRI_HEADERS)
        _salvar(client, _plano("Do Bruno"), headers=OUTRO_NUTRI_HEADERS)

        do_bruno, da_ana = _historico(client)

        assert da_ana["autor"] == {"id": NUTRI, "nome": "Dra. Ana"}
        assert do_bruno["autor"] == {"id": OUTRO_NUTRI, "nome": "Dr. Bruno"}
        assert da_ana["nutricionista_id"] == NUTRI

    def test_autor_nulo_quando_a_conta_foi_removida(self, client: TestClient, db: Session) -> None:
        db.add(Vinculo(status="ativo", nutricionista_id=OUTRO_NUTRI, paciente_id=PACIENTE))
        db.commit()
        _salvar(client, _plano("Da Ana"), headers=NUTRI_HEADERS)
        db.execute(delete(Usuario).where(Usuario.id == NUTRI))
        db.commit()

        (versao,) = _historico(client, headers=OUTRO_NUTRI_HEADERS)

        assert versao["autor"] is None
        assert versao["titulo"] == "Da Ana", "a versao continua no historico"


class TestAcesso:
    ROTA = f"{API}/{PACIENTE}/planos/versoes"

    def test_exige_token(self, client: TestClient) -> None:
        assert client.get(self.ROTA).status_code == 401

    def test_paciente_nao_consulta_o_historico(self, client: TestClient) -> None:
        resposta = client.get(self.ROTA, headers=factories.headers_de(PACIENTE, "paciente"))

        assert resposta.status_code == 403
        assert resposta.json()["detail"] == "Perfil nao autorizado"

    def test_nutricionista_sem_vinculo_recebe_403(self, client: TestClient) -> None:
        resposta = client.get(self.ROTA, headers=OUTRO_NUTRI_HEADERS)

        assert resposta.status_code == 403
        assert resposta.json()["detail"] == "Sem vinculo com este paciente"

    def test_paciente_inexistente_da_404(self, client: TestClient) -> None:
        resposta = client.get(f"{API}/999/planos/versoes", headers=NUTRI_HEADERS)

        assert resposta.status_code == 404
        assert resposta.json()["detail"] == "Paciente nao encontrado"

    def test_recusa_id_de_paciente_invalido(self, client: TestClient) -> None:
        assert client.get(f"{API}/0/planos/versoes", headers=NUTRI_HEADERS).status_code == 422
