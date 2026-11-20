"""Direitos do titular (LGPD, RF28): consentimento, exportacao e exclusao da conta.

A exportacao devolvia 500 sempre que o titular tinha algum dado: o servico
colocava objetos do banco na resposta. Nenhuma dessas rotas tinha teste.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.alimento_personalizado import AlimentoPersonalizado
from app.models.historico_xp import HistoricoXP
from app.models.paciente import Paciente
from app.models.usuario import Usuario
from app.models.vinculo import Vinculo
from tests import factories

API = "/api/v1/privacidade"
PACIENTE, NUTRI = 1, 10


def _paciente_com_dados(db: Session) -> Paciente:
    paciente = factories.criar_paciente(db, PACIENTE)
    factories.criar_nutricionista(db, NUTRI)
    paciente.peso_kg = Decimal("72.5")
    paciente.altura_cm = Decimal("170")
    paciente.idade = 31
    paciente.genero = "feminino"
    paciente.nivel_atividade = "moderado"
    paciente.meta_kcal = Decimal("1900")
    paciente.xp = 40
    db.add(Vinculo(nutricionista_id=NUTRI, paciente_id=PACIENTE, status="ativo"))
    db.add(
        AlimentoPersonalizado(
            paciente_id=PACIENTE,
            nome="Bolo da vo",
            kcal_100g=Decimal("320"),
            carbs_100g=Decimal("50"),
            prot_100g=Decimal("6"),
            gord_100g=Decimal("11"),
        )
    )
    db.add(HistoricoXP(paciente_id=PACIENTE, quantidade=40, motivo="refeicao"))
    db.commit()
    return paciente


def test_exportacao_do_paciente_traz_todos_os_blocos(client: TestClient, db: Session) -> None:
    _paciente_com_dados(db)
    headers = factories.headers_de(PACIENTE)
    client.post(f"{API}/consentimento", json={"versao_termo": "v1"}, headers=headers)
    refeicao = factories.refeicao(PACIENTE, datetime.now(UTC) - timedelta(hours=2))
    assert client.post("/api/v1/refeicoes", json=refeicao, headers=headers).status_code == 201

    resposta = client.get(f"{API}/dados", headers=headers)

    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["usuario"]["email"] == "paciente1@exemplo.com"
    assert dados["paciente"]["peso_kg"] == 72.5
    assert dados["paciente"]["genero"] == "feminino"
    assert dados["paciente"]["meta_kcal"] == 1900
    assert [c["versao_termo"] for c in dados["consentimentos"]] == ["v1"]
    assert len(dados["refeicoes"]) == 1
    assert dados["refeicoes"][0]["itens"][0]["nome_alimento"] == "Arroz branco cozido"
    assert dados["refeicoes"][0]["totais"]["calorias_kcal"] == 193.5
    assert [a["nome"] for a in dados["alimentos_personalizados"]] == ["Bolo da vo"]
    assert dados["historico_xp"][0]["quantidade"] == 40
    assert dados["vinculos"] == [
        {
            "nutricionista_id": NUTRI,
            "paciente_id": PACIENTE,
            "status": "ativo",
            "criado_em": dados["vinculos"][0]["criado_em"],
        }
    ]
    assert "senha_hash" not in str(dados)


def test_exportacao_do_nutricionista_traz_so_conta_e_vinculos(
    client: TestClient, db: Session
) -> None:
    _paciente_com_dados(db)

    resposta = client.get(f"{API}/dados", headers=factories.headers_de(NUTRI, "nutricionista"))

    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["usuario"]["perfil"] == "nutricionista"
    assert dados["paciente"] is None
    assert dados["refeicoes"] == []
    assert len(dados["vinculos"]) == 1


def test_exportacao_de_conta_sem_dados(client: TestClient, db: Session) -> None:
    factories.criar_paciente(db, PACIENTE)

    resposta = client.get(f"{API}/dados", headers=factories.headers_de(PACIENTE))

    assert resposta.status_code == 200
    assert resposta.json()["refeicoes"] == []


def test_consentimento_aceite_e_revogacao(client: TestClient, db: Session) -> None:
    factories.criar_paciente(db, PACIENTE)
    headers = factories.headers_de(PACIENTE)

    assert client.get(f"{API}/consentimento", headers=headers).json() == {
        "consentimentos": [],
        "consentimento_ativo": False,
    }
    assert client.post(f"{API}/consentimento/revogar", headers=headers).status_code == 404

    aceite = client.post(f"{API}/consentimento", json={"versao_termo": " v2 "}, headers=headers)
    assert aceite.status_code == 201
    assert aceite.json()["versao_termo"] == "v2"
    assert client.get(f"{API}/consentimento", headers=headers).json()["consentimento_ativo"]

    revogado = client.post(f"{API}/consentimento/revogar", headers=headers)
    assert revogado.status_code == 200
    assert revogado.json()["revogado_em"] is not None
    assert not client.get(f"{API}/consentimento", headers=headers).json()["consentimento_ativo"]


def test_exclusao_da_conta_apaga_o_titular(client: TestClient, db: Session) -> None:
    _paciente_com_dados(db)
    headers = factories.headers_de(PACIENTE)

    assert client.delete(f"{API}/conta", headers=headers).status_code == 204

    db.expire_all()
    assert db.get(Usuario, PACIENTE) is None
    assert db.query(AlimentoPersonalizado).count() == 0
    assert client.get(f"{API}/dados", headers=headers).status_code == 401


def test_rotas_do_titular_exigem_login(client: TestClient) -> None:
    for metodo, rota in [
        ("GET", "/dados"),
        ("GET", "/consentimento"),
        ("POST", "/consentimento/revogar"),
        ("DELETE", "/conta"),
    ]:
        assert client.request(metodo, API + rota).status_code == 401
