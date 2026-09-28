"""Testes da categorizacao de refeicoes (RF19)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.models.refeicao import TipoRefeicao
from app.services.refeicoes import sugerir_tipo
from tests import factories

ROTA = "/api/v1/refeicoes"


def _criar(client: TestClient, **kwargs: Any) -> dict[str, Any]:
    resposta = client.post(ROTA, json=factories.refeicao(**kwargs))
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def _em(hora: int) -> datetime:
    """Um horario de ontem (garante que nunca cai no futuro) na hora dada, em UTC."""
    return (datetime.now(UTC) - timedelta(days=1)).replace(
        hour=hora, minute=0, second=0, microsecond=0
    )


class TestSugestaoDeTipo:
    """Unidade: a funcao pura que decide o tipo a partir do horario."""

    @pytest.mark.parametrize(
        ("hora", "esperado"),
        [
            (5, TipoRefeicao.CAFE_DA_MANHA),
            (8, TipoRefeicao.CAFE_DA_MANHA),
            (10, TipoRefeicao.CAFE_DA_MANHA),
            (11, TipoRefeicao.ALMOCO),
            (13, TipoRefeicao.ALMOCO),
            (14, TipoRefeicao.ALMOCO),
            (15, TipoRefeicao.LANCHE),
            (17, TipoRefeicao.LANCHE),
            (18, TipoRefeicao.JANTAR),
            (20, TipoRefeicao.JANTAR),
            (21, TipoRefeicao.JANTAR),
            (22, TipoRefeicao.LANCHE),
            (2, TipoRefeicao.LANCHE),
        ],
    )
    def test_sugere_pelo_horario(self, hora: int, esperado: TipoRefeicao) -> None:
        assert sugerir_tipo(_em(hora)) == esperado


class TestTipoAoRegistrar:
    def test_sugere_automaticamente_quando_nao_informado(self, client: TestClient) -> None:
        corpo = _criar(client, consumida_em=_em(8))

        assert corpo["tipo"] == "cafe_da_manha"

    def test_respeita_tipo_informado_mesmo_fora_da_janela_tipica(self, client: TestClient) -> None:
        # Horario de cafe da manha, mas o paciente marcou como lanche.
        corpo = _criar(client, consumida_em=_em(8), tipo="lanche")

        assert corpo["tipo"] == "lanche"

    def test_recusa_tipo_invalido(self, client: TestClient) -> None:
        resposta = client.post(ROTA, json=factories.refeicao(tipo="brunch"))

        assert resposta.status_code == 422

    def test_atualiza_tipo(self, client: TestClient) -> None:
        criada = _criar(client, consumida_em=_em(8))
        assert criada["tipo"] == "cafe_da_manha"

        resposta = client.put(f"{ROTA}/{criada['id']}", json={"tipo": "lanche"})

        assert resposta.status_code == 200
        assert resposta.json()["tipo"] == "lanche"


class TestFiltroPorTipo:
    def test_lista_apenas_o_tipo_filtrado(self, client: TestClient) -> None:
        _criar(client, consumida_em=_em(8))  # cafe_da_manha (sugerido)
        _criar(client, consumida_em=_em(19))  # jantar (sugerido)

        resposta = client.get(ROTA, params={"paciente_id": 1, "tipo": "jantar"})

        assert resposta.status_code == 200
        corpo = resposta.json()
        assert len(corpo) == 1
        assert corpo[0]["tipo"] == "jantar"

    def test_sem_filtro_lista_todos_os_tipos(self, client: TestClient) -> None:
        _criar(client, consumida_em=_em(8))
        _criar(client, consumida_em=_em(19))

        resposta = client.get(ROTA, params={"paciente_id": 1})

        assert len(resposta.json()) == 2

    def test_consumo_diario_filtra_por_tipo(self, client: TestClient) -> None:
        dia = _em(8)  # sempre no passado (ontem), evita cair no futuro
        cafe = factories.item(calorias="300.00")
        jantar = factories.item(calorias="700.00")

        _criar(client, consumida_em=dia, itens=[cafe])
        _criar(client, consumida_em=dia.replace(hour=19), itens=[jantar])

        resposta = client.get(
            f"{ROTA}/consumo-diario",
            params={"paciente_id": 1, "data": dia.date().isoformat(), "tipo": "jantar"},
        )

        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["quantidade_refeicoes"] == 1
        assert corpo["totais"]["calorias_kcal"] == 700.0
