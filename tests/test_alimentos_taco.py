"""Testes da busca no Banco Nutricional TACO (RF02.2)."""

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.alimento_taco import AlimentoTaco

ROTA = "/api/v1/alimentos-taco"


def _alimento(nome: str, categoria: str = "Cereais e derivados") -> AlimentoTaco:
    return AlimentoTaco(
        nome=nome,
        categoria=categoria,
        kcal_100g=Decimal("100.00"),
        carbs_100g=Decimal("20.00"),
        prot_100g=Decimal("5.00"),
        gord_100g=Decimal("1.00"),
    )


class TestBusca:
    def test_encontra_por_trecho_do_nome(self, client: TestClient, db: Session) -> None:
        db.add_all(
            [
                _alimento("Arroz, tipo 1, cozido"),
                _alimento("Feijao, carioca, cozido"),
            ]
        )
        db.commit()

        resposta = client.get(ROTA, params={"nome": "arroz"})

        assert resposta.status_code == 200
        corpo = resposta.json()
        assert len(corpo) == 1
        assert corpo[0]["nome"] == "Arroz, tipo 1, cozido"

    def test_busca_e_case_insensitive(self, client: TestClient, db: Session) -> None:
        db.add(_alimento("Frango, peito, sem pele, cru", categoria="Carnes e derivados"))
        db.commit()

        resposta = client.get(ROTA, params={"nome": "FRANGO"})

        assert resposta.status_code == 200
        assert len(resposta.json()) == 1

    def test_valores_nutricionais_sao_numeros_no_json(
        self, client: TestClient, db: Session
    ) -> None:
        db.add(_alimento("Banana, prata, crua", categoria="Frutas e derivados"))
        db.commit()

        resposta = client.get(ROTA, params={"nome": "banana"})

        item = resposta.json()[0]
        assert item["kcal_100g"] == 100.0
        assert isinstance(item["kcal_100g"], float)

    def test_sem_resultado_retorna_lista_vazia(self, client: TestClient) -> None:
        resposta = client.get(ROTA, params={"nome": "alimento-inexistente"})

        assert resposta.status_code == 200
        assert resposta.json() == []

    def test_recusa_nome_vazio(self, client: TestClient) -> None:
        resposta = client.get(ROTA, params={"nome": ""})

        assert resposta.status_code == 422

    def test_respeita_limite_e_deslocamento(self, client: TestClient, db: Session) -> None:
        db.add_all([_alimento(f"Alimento teste {i}") for i in range(5)])
        db.commit()

        pagina_1 = client.get(ROTA, params={"nome": "alimento teste", "limite": 2}).json()
        pagina_2 = client.get(
            ROTA, params={"nome": "alimento teste", "limite": 2, "deslocamento": 2}
        ).json()

        assert len(pagina_1) == 2
        assert len(pagina_2) == 2
        assert {item["nome"] for item in pagina_1}.isdisjoint({item["nome"] for item in pagina_2})
