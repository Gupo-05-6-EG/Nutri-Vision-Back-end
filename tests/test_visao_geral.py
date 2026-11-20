"""Visao geral da carteira e vinculos pendentes para o nutricionista (B6, P1)."""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.tempo import FUSO
from app.models.alerta_desvio import AlertaDesvioPlano
from app.models.refeicao import ItemRefeicao, Refeicao
from app.models.usuario import Usuario
from app.models.vinculo import Vinculo
from tests import factories

NUTRI = 10
URL = "/api/v1/nutricionista/visao-geral"
HOJE = datetime.now(FUSO).date()


def _h() -> dict[str, str]:
    return factories.headers_de(NUTRI, "nutricionista")


def _refeicao(db: Session, paciente_id: int, dia: date, hora: int, kcal: str) -> None:
    db.add(
        Refeicao(
            paciente_id=paciente_id,
            consumida_em=datetime.combine(dia, time(hora), tzinfo=FUSO).astimezone(UTC),
            tipo="almoco",
            itens=[
                ItemRefeicao(
                    nome_alimento="Prato",
                    quantidade_g=Decimal("300"),
                    calorias_kcal=Decimal(kcal),
                    proteinas_g=Decimal("0"),
                    carboidratos_g=Decimal("0"),
                    gorduras_g=Decimal("0"),
                )
            ],
        )
    )


@pytest.fixture(autouse=True)
def _carteira(db: Session) -> None:
    """1 (Ana): ativa e dentro da meta; 2 (Bruno): ativo, sem registro ha dias;
    3 (Carla): ativa com alerta nao lido; 4 (Davi): pendente; 5: de outro nutricionista."""
    factories.criar_nutricionista(db, NUTRI)
    factories.criar_nutricionista(db, 11)
    nomes = {1: "Ana Lima", 2: "Bruno Castro", 3: "Carla Conceição", 4: "Davi Prado", 5: "Eva"}
    for pid, nome in nomes.items():
        paciente = factories.criar_paciente(db, pid)
        db.get(Usuario, pid).nome = nome
        paciente.meta_kcal = Decimal("2000")
        paciente.streak = pid
    for pid, status in [(1, "ativo"), (2, "ativo"), (3, "ativo"), (4, "pendente")]:
        db.add(Vinculo(nutricionista_id=NUTRI, paciente_id=pid, status=status))
    db.add(Vinculo(nutricionista_id=11, paciente_id=5, status="ativo"))
    for n in range(1, 8):  # Ana: 7 dias completos dentro da meta
        dia = HOJE - timedelta(days=n)
        _refeicao(db, 1, dia, 8, "900")
        _refeicao(db, 1, dia, 13, "1000")
    _refeicao(db, 1, HOJE, 0, "500")  # 00h: sempre no passado
    _refeicao(db, 2, HOJE - timedelta(days=5), 12, "800")
    _refeicao(db, 3, HOJE - timedelta(days=1), 12, "300")
    db.add(
        AlertaDesvioPlano(
            nutricionista_id=NUTRI,
            paciente_id=3,
            data_referencia=HOJE - timedelta(days=1),
            direcao="abaixo",
            dias_consecutivos=2,
            percentual_limite=Decimal("20"),
            percentual_medio_desvio=Decimal("85"),
            meta_kcal=Decimal("2000"),
            consumo_medio_kcal=Decimal("300"),
        )
    )
    db.commit()


def test_indicadores_e_situacao_de_cada_paciente(client: TestClient) -> None:
    resposta = client.get(URL, headers=_h())

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["contagens"] == {"todos": 4, "ativos": 3, "em_risco": 2, "pendentes": 1}
    assert corpo["indicadores"]["pacientes_ativos"] == 3
    assert corpo["indicadores"]["pacientes_pendentes"] == 1
    assert corpo["indicadores"]["alertas_criticos"] == 2
    assert corpo["indicadores"]["ofensiva_media_dias"] == 2.0  # (1 + 2 + 3) / 3
    por_id = {p["paciente_id"]: p for p in corpo["pacientes"]}
    assert set(por_id) == {1, 2, 3, 4}  # o paciente de outro nutricionista nao aparece

    ana = por_id[1]
    assert (ana["situacao"], ana["motivo_risco"]) == ("ativo", None)
    assert ana["adesao_semanal_pct"] == 100.0
    assert ana["consumo_hoje_kcal"] == 500.0
    assert ana["meta_kcal"] == 2000.0
    assert ana["ultimo_registro"]["tipo"] == "almoco"

    assert (por_id[2]["situacao"], por_id[2]["motivo_risco"]) == ("em_risco", "sem_registro")
    assert por_id[2]["adesao_semanal_pct"] == 0.0
    assert (por_id[3]["situacao"], por_id[3]["motivo_risco"]) == ("em_risco", "alerta_desvio")
    assert por_id[3]["alertas_nao_lidos"] == 1
    assert por_id[4]["situacao"] == "pendente"
    assert por_id[4]["meta_kcal"] is None  # sem vinculo ativo, sem dados de saude
    assert corpo["indicadores"]["adesao_media_pct"] == pytest.approx((100 + 0 + 0) / 3, abs=0.1)


@pytest.mark.parametrize(
    ("filtro", "ids"),
    [("ativos", [1, 2, 3]), ("em_risco", [2, 3]), ("pendentes", [4]), ("todos", [1, 2, 3, 4])],
)
def test_filtros(client: TestClient, filtro: str, ids: list[int]) -> None:
    corpo = client.get(URL, params={"status": filtro}, headers=_h()).json()

    assert [p["paciente_id"] for p in corpo["pacientes"]] == ids
    assert corpo["total"] == len(ids)
    assert corpo["contagens"]["todos"] == 4  # contagens sempre completas


def test_busca_e_paginacao(client: TestClient) -> None:
    busca = client.get(URL, params={"busca": "conceicao"}, headers=_h()).json()
    assert [p["nome"] for p in busca["pacientes"]] == ["Carla Conceição"]

    pagina = client.get(URL, params={"por_pagina": 2, "pagina": 2}, headers=_h()).json()
    assert [p["paciente_id"] for p in pagina["pacientes"]] == [3, 4]
    assert (pagina["total"], pagina["pagina"], pagina["por_pagina"]) == (4, 2, 2)


def test_so_nutricionista(client: TestClient) -> None:
    assert client.get(URL).status_code == 401
    assert client.get(URL, headers=factories.headers_de(1)).status_code == 403


def test_patients_lista_pendentes_pelo_status(client: TestClient) -> None:
    rota = "/api/v1/patients"

    ativos = client.get(rota, headers=_h()).json()
    pendentes = client.get(rota, params={"status": "pendente"}, headers=_h()).json()
    todos = client.get(rota, params={"status": "todos"}, headers=_h()).json()

    assert [p["paciente_id"] for p in ativos] == [1, 2, 3]
    assert [(p["paciente_id"], p["status"]) for p in pendentes] == [(4, "pendente")]
    assert len(todos) == 4
    assert client.get(rota, params={"status": "x"}, headers=_h()).status_code == 422
