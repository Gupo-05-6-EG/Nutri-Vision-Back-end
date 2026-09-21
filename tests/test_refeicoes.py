from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient

from tests import factories

ROTA = "/api/v1/refeicoes"


def _criar(client: TestClient, **kwargs: Any) -> dict[str, Any]:
    resposta = client.post(ROTA, json=factories.refeicao(**kwargs))
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


class TestRegistro:
    def test_registra_refeicao_com_itens(self, client: TestClient) -> None:
        corpo = _criar(client, observacao="Almoco em casa")

        assert corpo["id"] > 0
        assert corpo["paciente_id"] == 1
        assert corpo["observacao"] == "Almoco em casa"
        assert len(corpo["itens"]) == 1
        assert corpo["itens"][0]["nome_alimento"] == "Arroz branco cozido"

    def test_valores_nutricionais_sao_numeros_no_json(self, client: TestClient) -> None:
        corpo = _criar(client)

        item = corpo["itens"][0]
        assert item["quantidade_g"] == 150.0
        assert item["calorias_kcal"] == 193.5
        assert isinstance(item["calorias_kcal"], float)
        assert isinstance(corpo["totais"]["calorias_kcal"], float)

    def test_totais_sao_a_soma_dos_itens(self, client: TestClient) -> None:
        corpo = _criar(
            client,
            itens=[
                factories.item(calorias="200.00", proteinas="10.00"),
                factories.item(nome="Feijao", calorias="100.50", proteinas="5.25"),
            ],
        )

        assert corpo["totais"]["calorias_kcal"] == 300.50
        assert corpo["totais"]["proteinas_g"] == 15.25

    def test_resposta_traz_o_fuso_horario(self, client: TestClient) -> None:
        corpo = _criar(client)

        consumida_em = corpo["consumida_em"]
        assert consumida_em.endswith("+00:00") or consumida_em.endswith("Z")

    def test_recusa_refeicao_sem_itens(self, client: TestClient) -> None:
        resposta = client.post(ROTA, json=factories.refeicao(itens=[]))

        assert resposta.status_code == 422

    def test_recusa_quantidade_zero(self, client: TestClient) -> None:
        payload = factories.refeicao(itens=[factories.item(quantidade_g="0")])

        assert client.post(ROTA, json=payload).status_code == 422

    def test_recusa_macro_negativo(self, client: TestClient) -> None:
        payload = factories.refeicao(itens=[factories.item(proteinas="-1.00")])

        assert client.post(ROTA, json=payload).status_code == 422

    def test_recusa_nome_de_alimento_vazio(self, client: TestClient) -> None:
        payload = factories.refeicao(itens=[factories.item(nome="   ")])

        assert client.post(ROTA, json=payload).status_code == 422

    def test_recusa_consumo_no_futuro(self, client: TestClient) -> None:
        payload = factories.refeicao(consumida_em=datetime.now(UTC) + timedelta(days=1))

        resposta = client.post(ROTA, json=payload)

        assert resposta.status_code == 422
        assert "futuro" in resposta.json()["detail"]


class TestDetalheEEdicao:
    def test_detalha_refeicao(self, client: TestClient) -> None:
        criada = _criar(client)

        resposta = client.get(ROTA + "/" + str(criada["id"]))

        assert resposta.status_code == 200
        assert resposta.json()["id"] == criada["id"]

    def test_404_para_refeicao_inexistente(self, client: TestClient) -> None:
        assert client.get(ROTA + "/99999").status_code == 404

    def test_atualiza_itens_substituindo_os_antigos(self, client: TestClient) -> None:
        criada = _criar(client)

        resposta = client.put(
            ROTA + "/" + str(criada["id"]),
            json={"itens": [factories.item(nome="Banana", calorias="89.00")]},
        )

        assert resposta.status_code == 200
        corpo = resposta.json()
        assert [i["nome_alimento"] for i in corpo["itens"]] == ["Banana"]
        assert corpo["totais"]["calorias_kcal"] == 89.00

    def test_remove_refeicao_e_seus_itens(self, client: TestClient) -> None:
        criada = _criar(client)
        rota = ROTA + "/" + str(criada["id"])

        assert client.delete(rota).status_code == 204
        assert client.get(rota).status_code == 404

    def test_404_ao_remover_refeicao_inexistente(self, client: TestClient) -> None:
        assert client.delete(ROTA + "/99999").status_code == 404


class TestHistorico:
    def test_lista_apenas_as_refeicoes_do_paciente(self, client: TestClient) -> None:
        _criar(client, paciente_id=1)
        _criar(client, paciente_id=2)

        resposta = client.get(ROTA, params={"paciente_id": 1})

        assert resposta.status_code == 200
        assert [r["paciente_id"] for r in resposta.json()] == [1]

    def test_ordena_da_mais_recente_para_a_mais_antiga(self, client: TestClient) -> None:
        base = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)
        antiga = _criar(client, consumida_em=base)
        recente = _criar(client, consumida_em=base + timedelta(hours=6))

        corpo = client.get(ROTA, params={"paciente_id": 1}).json()

        assert [r["id"] for r in corpo] == [recente["id"], antiga["id"]]

    def test_filtra_por_dia(self, client: TestClient) -> None:
        _criar(client, consumida_em=datetime(2026, 9, 18, 23, 30, tzinfo=UTC))
        do_dia = _criar(client, consumida_em=datetime(2026, 9, 19, 8, 0, tzinfo=UTC))
        _criar(client, consumida_em=datetime(2026, 9, 20, 0, 30, tzinfo=UTC))

        corpo = client.get(ROTA, params={"paciente_id": 1, "data": "2026-09-19"}).json()

        assert [r["id"] for r in corpo] == [do_dia["id"]]

    def test_pagina_os_resultados(self, client: TestClient) -> None:
        base = datetime(2026, 9, 19, 8, 0, tzinfo=UTC)
        for hora in range(3):
            _criar(client, consumida_em=base + timedelta(hours=hora))

        primeira = client.get(ROTA, params={"paciente_id": 1, "limite": 2}).json()
        segunda = client.get(ROTA, params={"paciente_id": 1, "limite": 2, "deslocamento": 2}).json()

        assert len(primeira) == 2
        assert len(segunda) == 1
        assert {r["id"] for r in primeira}.isdisjoint({r["id"] for r in segunda})

    def test_exige_paciente_id(self, client: TestClient) -> None:
        assert client.get(ROTA).status_code == 422


class TestConsumoDiario:
    ROTA_DIARIO = ROTA + "/consumo-diario"

    def test_soma_os_totais_do_dia(self, client: TestClient) -> None:
        dia = datetime(2026, 9, 19, 8, 0, tzinfo=UTC)
        _criar(client, consumida_em=dia, itens=[factories.item(calorias="200.00")])
        _criar(
            client,
            consumida_em=dia + timedelta(hours=5),
            itens=[
                factories.item(nome="Feijao", calorias="100.00"),
                factories.item(nome="Frango", calorias="50.50"),
            ],
        )

        corpo = client.get(self.ROTA_DIARIO, params={"paciente_id": 1, "data": "2026-09-19"}).json()

        assert corpo["data"] == "2026-09-19"
        assert corpo["quantidade_refeicoes"] == 2
        assert corpo["totais"]["calorias_kcal"] == 350.50
        assert len(corpo["refeicoes"]) == 2

    def test_ignora_refeicoes_de_outros_dias(self, client: TestClient) -> None:
        _criar(client, consumida_em=datetime(2026, 9, 18, 20, 0, tzinfo=UTC))
        _criar(
            client,
            consumida_em=datetime(2026, 9, 19, 10, 0, tzinfo=UTC),
            itens=[factories.item(calorias="120.00")],
        )

        corpo = client.get(self.ROTA_DIARIO, params={"paciente_id": 1, "data": "2026-09-19"}).json()

        assert corpo["quantidade_refeicoes"] == 1
        assert corpo["totais"]["calorias_kcal"] == 120.00

    def test_dia_sem_registro_devolve_zeros(self, client: TestClient) -> None:
        corpo = client.get(self.ROTA_DIARIO, params={"paciente_id": 1, "data": "2026-01-01"}).json()

        assert corpo["quantidade_refeicoes"] == 0
        assert corpo["refeicoes"] == []
        assert corpo["totais"] == {
            "calorias_kcal": 0,
            "proteinas_g": 0,
            "carboidratos_g": 0,
            "gorduras_g": 0,
        }

    def test_ignora_refeicoes_de_outro_paciente(self, client: TestClient) -> None:
        dia = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
        _criar(client, paciente_id=1, consumida_em=dia)
        _criar(client, paciente_id=2, consumida_em=dia)

        corpo = client.get(self.ROTA_DIARIO, params={"paciente_id": 2, "data": "2026-09-19"}).json()

        assert corpo["quantidade_refeicoes"] == 1
        assert corpo["refeicoes"][0]["paciente_id"] == 2
