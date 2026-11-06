"""Testes do mapeamento IA -> TACO e do calculo por porcao (RF03, RF20, RF21)."""

import csv
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.alimento_taco import AlimentoTaco
from app.services.calculo_nutricional import CSV_PATH, carregar_mapeamento

ROTA = "/api/v1/calculo-nutricional"


def _taco(nome: str, kcal: str, carbs: str, prot: str, gord: str) -> AlimentoTaco:
    return AlimentoTaco(
        nome=nome,
        categoria="Teste",
        kcal_100g=Decimal(kcal),
        carbs_100g=Decimal(carbs),
        prot_100g=Decimal(prot),
        gord_100g=Decimal(gord),
    )


def _popular(db: Session) -> None:
    db.add_all(
        [
            _taco("Arroz, tipo 1, cozido", "128.00", "28.10", "2.50", "0.20"),
            _taco("Batata, inglesa, cozida", "52.00", "11.90", "1.20", "0.00"),
            _taco("Batata, inglesa, frita", "267.00", "35.60", "5.00", "13.10"),
        ]
    )
    db.commit()


def _item(classe: str, preparo: str, gramas: str) -> dict[str, str]:
    return {"classe": classe, "metodo_preparo": preparo, "gramas": gramas}


class TestCalculo:
    def test_aplica_valor_por_100g_vezes_gramas_sobre_100(
        self, client: TestClient, db: Session
    ) -> None:
        _popular(db)

        resposta = client.post(ROTA, json={"itens": [_item("arroz", "cozido", "150")]})

        assert resposta.status_code == 200
        item = resposta.json()["itens"][0]
        assert item["alimento_taco"] == "Arroz, tipo 1, cozido"
        assert item["calorias_kcal"] == 192.0
        assert item["carboidratos_g"] == 42.15
        assert item["proteinas_g"] == 3.75
        assert item["gorduras_g"] == 0.3

    def test_metodo_de_preparo_escolhe_a_linha_da_taco(
        self, client: TestClient, db: Session
    ) -> None:
        _popular(db)

        corpo = client.post(
            ROTA,
            json={
                "itens": [
                    _item("batata_inglesa", "cozido", "100"),
                    _item("batata_inglesa", "frito", "100"),
                ]
            },
        ).json()

        assert [i["calorias_kcal"] for i in corpo["itens"]] == [52.0, 267.0]

    def test_totais_somam_os_itens(self, client: TestClient, db: Session) -> None:
        _popular(db)

        corpo = client.post(
            ROTA,
            json={
                "itens": [_item("arroz", "cozido", "150"), _item("batata_inglesa", "frito", "80")]
            },
        ).json()

        assert corpo["totais"]["calorias_kcal"] == 405.6
        assert corpo["totais"]["gorduras_g"] == 10.78
        assert isinstance(corpo["totais"]["calorias_kcal"], float)

    def test_classe_e_normalizada(self, client: TestClient, db: Session) -> None:
        _popular(db)

        resposta = client.post(ROTA, json={"itens": [_item("  Arroz ", "cozido", "100")]})

        assert resposta.status_code == 200
        assert resposta.json()["itens"][0]["classe"] == "arroz"


class TestErros:
    def test_combinacao_sem_mapeamento_da_422(self, client: TestClient, db: Session) -> None:
        _popular(db)

        resposta = client.post(ROTA, json={"itens": [_item("arroz", "frito", "100")]})

        assert resposta.status_code == 422
        assert "arroz" in resposta.json()["detail"]

    def test_classe_desconhecida_da_422(self, client: TestClient) -> None:
        resposta = client.post(ROTA, json={"itens": [_item("unicornio", "cru", "100")]})

        assert resposta.status_code == 422

    def test_alimento_fora_do_banco_da_404(self, client: TestClient) -> None:
        resposta = client.post(ROTA, json={"itens": [_item("arroz", "cozido", "100")]})

        assert resposta.status_code == 404

    def test_recusa_gramas_invalidas(self, client: TestClient) -> None:
        assert client.post(ROTA, json={"itens": [_item("arroz", "cozido", "0")]}).status_code == 422

    def test_recusa_metodo_de_preparo_invalido(self, client: TestClient) -> None:
        resposta = client.post(ROTA, json={"itens": [_item("arroz", "assado", "100")]})

        assert resposta.status_code == 422

    def test_recusa_lista_vazia(self, client: TestClient) -> None:
        assert client.post(ROTA, json={"itens": []}).status_code == 422


def test_todo_de_para_aponta_para_um_alimento_existente_na_taco() -> None:
    """Protege o CSV de de-para contra erro de digitacao no nome da TACO."""
    taco = _nomes_da_taco()
    faltando = [nome for nome in carregar_mapeamento().values() if nome not in taco]

    assert faltando == []


def _nomes_da_taco() -> set[str]:
    with (CSV_PATH.parent / "taco.csv").open(encoding="utf-8") as arquivo:
        return {linha["nome"].strip() for linha in csv.DictReader(arquivo)}
