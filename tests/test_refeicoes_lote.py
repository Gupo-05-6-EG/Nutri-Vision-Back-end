"""Testes da sincronizacao em lote de refeicoes offline (Task 2.3 [Back], RNF07)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.refeicao import Refeicao
from tests import factories

ROTA = "/api/v1/refeicoes"
ROTA_LOTE = f"{ROTA}/batch"
BASE = datetime(2026, 10, 20, 12, 30, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _pacientes(db: Session) -> None:
    factories.criar_paciente(db, 1)
    factories.criar_paciente(db, 2)


@pytest.fixture(autouse=True)
def _logado_como_paciente_1(client: TestClient) -> None:
    client.headers.update(factories.headers_de(1))


def _refeicao(minutos: int = 0, **kwargs: Any) -> dict[str, Any]:
    kwargs.setdefault("consumida_em", BASE + timedelta(minutes=minutos))
    kwargs.setdefault("tipo", "almoco")
    return factories.refeicao(**kwargs)


def _lote(*refeicoes: dict[str, Any], paciente_id: int = 1) -> dict[str, Any]:
    return {"paciente_id": paciente_id, "refeicoes": list(refeicoes)}


def _enviar(client: TestClient, lote: dict[str, Any]) -> dict[str, Any]:
    resposta = client.post(ROTA_LOTE, json=lote)
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def _total_refeicoes(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Refeicao))


class TestCriacao:
    def test_cria_todas_e_devolve_na_ordem_do_envio(self, client: TestClient, db: Session) -> None:
        corpo = _enviar(
            client,
            _lote(
                _refeicao(0, tipo="cafe_da_manha"),
                _refeicao(60, tipo="almoco"),
                _refeicao(120, tipo="jantar"),
            ),
        )

        assert corpo["paciente_id"] == 1
        assert corpo["criadas"] == 3
        assert corpo["duplicadas"] == 0
        refeicoes = corpo["refeicoes"]
        assert [r["tipo"] for r in refeicoes] == ["cafe_da_manha", "almoco", "jantar"]
        assert all(isinstance(r["id"], int) for r in refeicoes)
        assert len({r["id"] for r in refeicoes}) == 3
        assert not any(r["duplicada"] for r in refeicoes)
        assert _total_refeicoes(db) == 3

    def test_refeicoes_do_lote_aparecem_no_historico(self, client: TestClient) -> None:
        corpo = _enviar(client, _lote(_refeicao(0), _refeicao(30)))

        historico = client.get(ROTA, params={"paciente_id": 1}).json()

        assert sorted(r["id"] for r in historico) == sorted(r["id"] for r in corpo["refeicoes"])

    def test_resposta_traz_itens_totais_e_fuso(self, client: TestClient) -> None:
        refeicao = _enviar(client, _lote(_refeicao(observacao="Feita offline")))["refeicoes"][0]

        assert refeicao["observacao"] == "Feita offline"
        assert refeicao["itens"][0]["nome_alimento"] == "Arroz branco cozido"
        assert refeicao["totais"]["calorias_kcal"] == 193.5
        assert refeicao["consumida_em"].endswith(("+00:00", "Z"))

    def test_tipo_omitido_usa_a_sugestao_pelo_horario(self, client: TestClient) -> None:
        sem_tipo = factories.refeicao(consumida_em=BASE.replace(hour=8))

        refeicao = _enviar(client, _lote(sem_tipo))["refeicoes"][0]

        assert refeicao["tipo"] == "cafe_da_manha"


class TestDeduplicacao:
    def test_reenviar_o_mesmo_lote_nao_duplica(self, client: TestClient, db: Session) -> None:
        lote = _lote(_refeicao(0), _refeicao(60, observacao="Lanche da tarde"))
        primeiro = _enviar(client, lote)

        segundo = _enviar(client, lote)

        assert segundo["criadas"] == 0
        assert segundo["duplicadas"] == 2
        assert [r["id"] for r in segundo["refeicoes"]] == [r["id"] for r in primeiro["refeicoes"]]
        assert all(r["duplicada"] for r in segundo["refeicoes"])
        assert _total_refeicoes(db) == 2

    def test_lote_com_parte_ja_sincronizada(self, client: TestClient, db: Session) -> None:
        ja_enviada = _enviar(client, _lote(_refeicao(0)))["refeicoes"][0]

        corpo = _enviar(client, _lote(_refeicao(0), _refeicao(60)))

        assert corpo["criadas"] == 1
        assert corpo["duplicadas"] == 1
        assert corpo["refeicoes"][0]["id"] == ja_enviada["id"]
        assert corpo["refeicoes"][0]["duplicada"] is True
        assert corpo["refeicoes"][1]["duplicada"] is False
        assert _total_refeicoes(db) == 2

    def test_repeticao_dentro_do_proprio_lote(self, client: TestClient, db: Session) -> None:
        corpo = _enviar(client, _lote(_refeicao(0), _refeicao(0)))

        primeira, repetida = corpo["refeicoes"]
        assert primeira["id"] == repetida["id"]
        assert (primeira["duplicada"], repetida["duplicada"]) == (False, True)
        assert corpo["criadas"] == 1
        assert _total_refeicoes(db) == 1

    def test_reconhece_refeicao_gravada_pelo_post_individual(
        self, client: TestClient, db: Session
    ) -> None:
        # O app tenta o POST individual com internet; se a resposta se perder,
        # a mesma refeicao volta depois no lote.
        individual = client.post(ROTA, json=_refeicao(0)).json()

        corpo = _enviar(client, _lote(_refeicao(0)))

        assert corpo["refeicoes"][0]["id"] == individual["id"]
        assert corpo["refeicoes"][0]["duplicada"] is True
        assert _total_refeicoes(db) == 1

    def test_ordem_dos_itens_nao_importa(self, client: TestClient) -> None:
        arroz = factories.item()
        feijao = factories.item(nome="Feijao", calorias="100.50")
        primeiro = _enviar(client, _lote(_refeicao(0, itens=[arroz, feijao])))

        segundo = _enviar(client, _lote(_refeicao(0, itens=[feijao, arroz])))

        assert segundo["refeicoes"][0]["id"] == primeiro["refeicoes"][0]["id"]
        assert segundo["refeicoes"][0]["duplicada"] is True

    def test_mesmo_valor_com_escala_diferente_e_duplicado(self, client: TestClient) -> None:
        primeiro = _enviar(client, _lote(_refeicao(0, itens=[factories.item(calorias="193.5")])))

        segundo = _enviar(client, _lote(_refeicao(0, itens=[factories.item(calorias="193.50")])))

        assert segundo["refeicoes"][0]["id"] == primeiro["refeicoes"][0]["id"]

    def test_tipo_omitido_tambem_deduplica(self, client: TestClient, db: Session) -> None:
        sem_tipo = factories.refeicao(consumida_em=BASE.replace(hour=8))

        _enviar(client, _lote(sem_tipo))
        corpo = _enviar(client, _lote(sem_tipo))

        assert corpo["refeicoes"][0]["duplicada"] is True
        assert _total_refeicoes(db) == 1

    @pytest.mark.parametrize(
        "diferenca",
        [
            {"consumida_em": BASE + timedelta(minutes=1)},
            {"tipo": "jantar"},
            {"observacao": "Outra observacao"},
            {"itens": [factories.item(quantidade_g="151.00")]},
            {"itens": [factories.item(), factories.item(nome="Feijao")]},
        ],
        ids=["horario", "tipo", "observacao", "quantidade", "itens_extras"],
    )
    def test_refeicoes_diferentes_nao_sao_deduplicadas(
        self, client: TestClient, db: Session, diferenca: dict[str, Any]
    ) -> None:
        _enviar(client, _lote(_refeicao(0)))

        corpo = _enviar(client, _lote(_refeicao(0, **diferenca)))

        assert corpo["refeicoes"][0]["duplicada"] is False
        assert _total_refeicoes(db) == 2

    def test_mesma_refeicao_de_outro_paciente_nao_e_duplicada(
        self, client: TestClient, db: Session
    ) -> None:
        _enviar(client, _lote(_refeicao(0)))

        resposta = client.post(
            ROTA_LOTE,
            json=_lote(_refeicao(0, paciente_id=2), paciente_id=2),
            headers=factories.headers_de(2),
        )

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["refeicoes"][0]["duplicada"] is False
        assert _total_refeicoes(db) == 2


class TestValidacaoEAcesso:
    def test_exige_token(self, client: TestClient) -> None:
        client.headers.pop("Authorization")

        resposta = client.post(ROTA_LOTE, json=_lote(_refeicao()))

        assert resposta.status_code == 401

    def test_recusa_lote_de_outro_paciente(self, client: TestClient, db: Session) -> None:
        resposta = client.post(ROTA_LOTE, json=_lote(_refeicao(paciente_id=2), paciente_id=2))

        assert resposta.status_code == 403
        assert _total_refeicoes(db) == 0

    def test_recusa_refeicao_de_outro_paciente_dentro_do_lote(
        self, client: TestClient, db: Session
    ) -> None:
        resposta = client.post(ROTA_LOTE, json=_lote(_refeicao(0), _refeicao(30, paciente_id=2)))

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == "refeicoes[1].paciente_id difere do paciente_id do lote"
        assert _total_refeicoes(db) == 0

    def test_recusa_lote_vazio(self, client: TestClient) -> None:
        resposta = client.post(ROTA_LOTE, json=_lote())

        assert resposta.status_code == 422

    def test_lote_e_tudo_ou_nada(self, client: TestClient, db: Session) -> None:
        no_futuro = _refeicao(consumida_em=datetime.now(UTC) + timedelta(days=1))

        resposta = client.post(ROTA_LOTE, json=_lote(_refeicao(0), _refeicao(30), no_futuro))

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == "refeicoes[2].consumida_em nao pode estar no futuro"
        assert _total_refeicoes(db) == 0

    def test_recusa_item_invalido_no_lote(self, client: TestClient, db: Session) -> None:
        invalida = _refeicao(itens=[factories.item(quantidade_g="0")])

        resposta = client.post(ROTA_LOTE, json=_lote(_refeicao(0), invalida))

        assert resposta.status_code == 422
        assert _total_refeicoes(db) == 0
