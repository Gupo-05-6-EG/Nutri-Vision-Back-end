"""Perfil do paciente e meta diaria unica (A3, A4, P1)."""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.historico_xp import HistoricoXP
from app.models.paciente import Paciente
from app.models.plano_alimentar import PlanoAlimentar, RefeicaoPlano
from app.models.vinculo import Vinculo
from app.services.perfil import classificar_imc, divisao_por_xp
from tests import factories

PACIENTE, NUTRI, OUTRO_NUTRI = 1, 10, 11
URL = f"/api/v1/pacientes/{PACIENTE}/perfil"


@pytest.fixture
def paciente(db: Session) -> Paciente:
    paciente = factories.criar_paciente(db, PACIENTE)
    factories.criar_nutricionista(db, NUTRI, nome="Dra. Camila Mendes")
    factories.criar_nutricionista(db, OUTRO_NUTRI)
    paciente.peso_kg = Decimal("78.4")
    paciente.altura_cm = Decimal("178")
    paciente.idade = 27
    paciente.genero = "masculino"
    paciente.nivel_atividade = "moderado"
    paciente.meta_kcal = Decimal("2500")
    paciente.xp = 520
    paciente.streak = 12
    db.commit()
    return paciente


def _plano(db: Session, kcal: str, proteinas: str) -> PlanoAlimentar:
    plano = PlanoAlimentar(
        paciente_id=PACIENTE,
        nutricionista_id=NUTRI,
        versao=1,
        titulo="Hipertrofia Limpa",
        ativo=True,
        refeicoes=[
            RefeicaoPlano(
                ordem=1,
                nome="Almoco",
                meta_kcal=Decimal(kcal),
                meta_proteinas_g=Decimal(proteinas),
            )
        ],
    )
    db.add(plano)
    db.commit()
    return plano


def test_perfil_sem_plano_usa_a_triagem(client: TestClient, paciente: Paciente) -> None:
    resposta = client.get(URL, headers=factories.headers_de(PACIENTE))

    assert resposta.status_code == 200
    perfil = resposta.json()
    assert perfil["nome"] == "Paciente 1"
    assert perfil["imc"] == 24.7
    assert perfil["classificacao_imc"] == "Eutrófico"
    assert perfil["tmb_kcal"] > 1800
    assert perfil["fator_atividade"] == 1.55
    # 20/50/30 sobre 2500 kcal
    assert perfil["meta"] == {
        "kcal": 2500,
        "proteinas_g": 125,
        "carboidratos_g": 312.5,
        "gorduras_g": 83.3,
        "origem": "triagem",
    }
    assert perfil["gamificacao"]["divisao"] == "Ouro"
    assert perfil["gamificacao"]["proxima_divisao"] == "Diamante"
    assert perfil["gamificacao"]["xp_para_proxima"] == 980
    assert perfil["nutricionista"] is None
    assert perfil["plano_ativo"] is None


def test_plano_ativo_tem_precedencia(client: TestClient, db: Session, paciente: Paciente) -> None:
    db.add(Vinculo(nutricionista_id=NUTRI, paciente_id=PACIENTE, status="ativo"))
    _plano(db, kcal="1800", proteinas="130")

    perfil = client.get(URL, headers=factories.headers_de(PACIENTE)).json()

    assert perfil["meta"]["origem"] == "plano"
    assert perfil["meta"]["kcal"] == 1800
    assert perfil["meta"]["proteinas_g"] == 130  # do plano
    assert perfil["meta"]["carboidratos_g"] == 225  # 50% de 1800 / 4
    assert perfil["nutricionista"] == {
        "id": NUTRI,
        "nome": "Dra. Camila Mendes",
        "crn": "CRN-3 00010",
    }
    assert perfil["plano_ativo"]["titulo"] == "Hipertrofia Limpa"


def test_sem_triagem_nem_plano_nao_ha_meta(client: TestClient, db: Session) -> None:
    factories.criar_paciente(db, PACIENTE)

    perfil = client.get(URL, headers=factories.headers_de(PACIENTE)).json()

    assert perfil["meta"]["kcal"] is None
    assert perfil["meta"]["origem"] is None
    assert perfil["imc"] is None
    assert perfil["tmb_kcal"] is None
    assert perfil["gamificacao"]["divisao"] == "Bronze"


def test_conta_refeicoes_registradas(client: TestClient, paciente: Paciente) -> None:
    headers = factories.headers_de(PACIENTE)
    client.post("/api/v1/refeicoes", json=factories.refeicao(PACIENTE), headers=headers)

    perfil = client.get(URL, headers=headers).json()

    assert perfil["gamificacao"]["refeicoes_registradas"] == 1


def test_acesso_so_do_paciente_ou_nutricionista_vinculado(
    client: TestClient, db: Session, paciente: Paciente
) -> None:
    db.add(Vinculo(nutricionista_id=NUTRI, paciente_id=PACIENTE, status="ativo"))
    db.add(HistoricoXP(paciente_id=PACIENTE, quantidade=10, motivo="x"))
    db.commit()

    assert client.get(URL, headers=factories.headers_de(NUTRI, "nutricionista")).status_code == 200
    assert (
        client.get(URL, headers=factories.headers_de(OUTRO_NUTRI, "nutricionista")).status_code
        == 403
    )
    assert client.get(URL).status_code == 401


@pytest.mark.parametrize(
    ("xp", "esperado"),
    [
        (0, ("Bronze", "Prata", 200)),
        (199, ("Bronze", "Prata", 1)),
        (200, ("Prata", "Ouro", 300)),
        (520, ("Ouro", "Diamante", 980)),
        (5000, ("Diamante", None, None)),
    ],
)
def test_divisoes(xp: int, esperado: tuple) -> None:
    assert divisao_por_xp(xp) == esperado


@pytest.mark.parametrize(
    ("imc", "faixa"),
    [
        ("17", "Abaixo do peso"),
        ("22", "Eutrófico"),
        ("27", "Sobrepeso"),
        ("41", "Obesidade grau III"),
    ],
)
def test_classificacao_imc(imc: str, faixa: str) -> None:
    assert classificar_imc(Decimal(imc)) == faixa


def test_perfil_mostra_o_convite_pendente(
    client: TestClient, db: Session, paciente: Paciente
) -> None:
    """Vinculo resgatado e nao aceito aparece como convite, sem dar acesso (BE-17)."""
    from app.models.vinculo import Vinculo

    db.add(Vinculo(nutricionista_id=NUTRI, paciente_id=PACIENTE, status="pendente"))
    db.commit()

    dados = client.get(URL, headers=factories.headers_de(PACIENTE)).json()

    assert dados["nutricionista"] is None
    assert dados["vinculo_pendente"]["id"] == NUTRI
    assert dados["vinculo_pendente"]["crn"]


def test_vinculo_ativo_nao_e_convite(client: TestClient, db: Session, paciente: Paciente) -> None:
    from app.models.vinculo import Vinculo

    db.add(Vinculo(nutricionista_id=NUTRI, paciente_id=PACIENTE, status="ativo"))
    db.commit()
    dados = client.get(URL, headers=factories.headers_de(PACIENTE)).json()

    assert dados["nutricionista"]["id"] == NUTRI
    assert dados["vinculo_pendente"] is None
