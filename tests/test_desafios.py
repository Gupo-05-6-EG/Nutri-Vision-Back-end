"""Testes dos desafios entre amigos (RF05.2, RF05.3)."""

from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import criar_token_acesso
from app.models.refeicao import ItemRefeicao, Refeicao, TipoRefeicao
from tests import factories

ROTA = "/api/v1/challenges"
INICIO = "2026-10-12T00:00:00-03:00"
FIM = "2026-10-13T00:00:00-03:00"


def _headers(usuario_id: int) -> dict[str, str]:
    token, _ = criar_token_acesso(usuario_id, "paciente")
    return {"Authorization": f"Bearer {token}"}


def _criar_refeicao(db: Session, paciente_id: int, tipo: TipoRefeicao, hora: int) -> None:
    db.add(
        Refeicao(
            paciente_id=paciente_id,
            consumida_em=datetime(2026, 10, 12, hora, tzinfo=UTC),
            tipo=tipo.value,
            itens=[
                ItemRefeicao(
                    nome_alimento="Item",
                    quantidade_g=Decimal("100"),
                    calorias_kcal=Decimal("100"),
                    proteinas_g=Decimal("1"),
                    carboidratos_g=Decimal("1"),
                    gorduras_g=Decimal("1"),
                )
            ],
        )
    )
    db.commit()


def test_criar_convidar_aceitar_e_consultar_placar(client: TestClient, db: Session) -> None:
    primeiro = factories.criar_paciente(db, 1)
    segundo = factories.criar_paciente(db, 2)
    primeiro.meta_kcal = segundo.meta_kcal = Decimal("2000")
    db.commit()

    criacao = client.post(
        ROTA,
        headers=_headers(1),
        json={
            "nome": "Semana equilibrada",
            "tipo": "refeicoes",
            "regra": "Completar as quatro categorias por dia",
            "inicio_em": INICIO,
            "fim_em": FIM,
            "convidados": [2],
        },
    )
    assert criacao.status_code == 201, criacao.text
    desafio_id = criacao.json()["id"]
    assert criacao.json()["status"] == "aceito"

    convites = client.get(ROTA, headers=_headers(2))
    assert convites.status_code == 200
    assert convites.json()[0]["status"] == "convidado"

    resposta = client.post(
        f"{ROTA}/{desafio_id}/response", headers=_headers(2), json={"aceitar": True}
    )
    assert resposta.status_code == 200
    assert resposta.json()["status"] == "aceito"

    for hora, tipo in enumerate(TipoRefeicao, start=8):
        _criar_refeicao(db, primeiro.id, tipo, hora)
    for hora, tipo in enumerate(list(TipoRefeicao)[:3], start=8):
        _criar_refeicao(db, segundo.id, tipo, hora)

    placar = client.get(f"{ROTA}/{desafio_id}/leaderboard", headers=_headers(1))
    assert placar.status_code == 200, placar.text
    assert [p["paciente_id"] for p in placar.json()["participantes"]] == [1, 2]
    assert [p["pontuacao"] for p in placar.json()["participantes"]] == [1, 0]


def test_convite_de_outro_paciente_nao_pode_ser_respondido(client: TestClient, db: Session) -> None:
    factories.criar_paciente(db, 1)
    factories.criar_paciente(db, 2)
    factories.criar_paciente(db, 3)
    criacao = client.post(
        ROTA,
        headers=_headers(1),
        json={
            "nome": "Desafio",
            "tipo": "sequencia_meta",
            "regra": "Maior sequência",
            "inicio_em": INICIO,
            "fim_em": FIM,
            "convidados": [2],
        },
    )
    desafio_id = criacao.json()["id"]

    resposta = client.post(
        f"{ROTA}/{desafio_id}/response", headers=_headers(3), json={"aceitar": True}
    )
    assert resposta.status_code == 404


def test_nutricionista_nao_pode_criar_desafio(client: TestClient, db: Session) -> None:
    factories.criar_nutricionista(db, 10)
    token, _ = criar_token_acesso(10, "nutricionista")

    resposta = client.post(
        ROTA,
        headers={"Authorization": f"Bearer {token}"},
        json={
            "nome": "Desafio",
            "tipo": "refeicoes",
            "regra": "Completar categorias",
            "inicio_em": INICIO,
            "fim_em": FIM,
        },
    )
    assert resposta.status_code == 403
