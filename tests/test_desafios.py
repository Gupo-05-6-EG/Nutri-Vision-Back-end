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


def _criar_desafio(
    client: TestClient, criador_id: int, tipo: str = "refeicoes", convidados: list[int] = ()
) -> int:
    resposta = client.post(
        ROTA,
        headers=_headers(criador_id),
        json={
            "nome": "Desafio",
            "tipo": tipo,
            "regra": "Regra",
            "inicio_em": INICIO,
            "fim_em": FIM,
            "convidados": list(convidados),
        },
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["id"]


def test_criador_convida_pacientes_depois_de_criar(client: TestClient, db: Session) -> None:
    for paciente_id in (1, 2, 3):
        factories.criar_paciente(db, paciente_id)
    desafio_id = _criar_desafio(client, 1)

    resposta = client.post(
        f"{ROTA}/{desafio_id}/invites", headers=_headers(1), json={"pacientes": [2, 3]}
    )

    assert resposta.status_code == 201, resposta.text
    assert sorted(p["paciente_id"] for p in resposta.json()) == [2, 3]
    assert {p["status"] for p in resposta.json()} == {"convidado"}


def test_convites_invalidos_sao_recusados(client: TestClient, db: Session) -> None:
    for paciente_id in (1, 2, 3):
        factories.criar_paciente(db, paciente_id)
    desafio_id = _criar_desafio(client, 1, convidados=[2])
    rota = f"{ROTA}/{desafio_id}/invites"

    assert (
        client.post(f"{ROTA}/999/invites", headers=_headers(1), json={"pacientes": [3]}).status_code
        == 404
    )
    assert client.post(rota, headers=_headers(2), json={"pacientes": [3]}).status_code == 403
    assert client.post(rota, headers=_headers(1), json={"pacientes": [1]}).status_code == 409
    assert client.post(rota, headers=_headers(1), json={"pacientes": [2]}).status_code == 409
    assert client.post(rota, headers=_headers(1), json={"pacientes": [3, 3]}).status_code == 409
    assert client.post(rota, headers=_headers(1), json={"pacientes": [404]}).status_code == 409


def test_criacao_com_dados_invalidos_retorna_409(client: TestClient, db: Session) -> None:
    factories.criar_paciente(db, 1)
    factories.criar_paciente(db, 2)
    base = {"nome": "Desafio", "tipo": "refeicoes", "regra": "Regra"}
    casos = [
        {"inicio_em": FIM, "fim_em": INICIO, "convidados": []},
        {"inicio_em": "2026-10-12T00:00:00", "fim_em": FIM, "convidados": []},
        {"inicio_em": INICIO, "fim_em": FIM, "convidados": [1]},
        {"inicio_em": INICIO, "fim_em": FIM, "convidados": [404]},
    ]
    for caso in casos:
        resposta = client.post(ROTA, headers=_headers(1), json=base | caso)
        assert resposta.status_code == 409, caso


def test_convite_recusado_nao_pode_ser_respondido_de_novo(client: TestClient, db: Session) -> None:
    factories.criar_paciente(db, 1)
    factories.criar_paciente(db, 2)
    desafio_id = _criar_desafio(client, 1, convidados=[2])
    rota = f"{ROTA}/{desafio_id}/response"

    recusa = client.post(rota, headers=_headers(2), json={"aceitar": False})
    assert recusa.status_code == 200
    assert recusa.json()["status"] == "recusado"
    assert client.post(rota, headers=_headers(2), json={"aceitar": True}).status_code == 409


def test_placar_exige_participacao_aceita(client: TestClient, db: Session) -> None:
    for paciente_id in (1, 2, 3):
        factories.criar_paciente(db, paciente_id)
    desafio_id = _criar_desafio(client, 1, convidados=[2])

    assert client.get(f"{ROTA}/999/leaderboard", headers=_headers(1)).status_code == 404
    assert client.get(f"{ROTA}/{desafio_id}/leaderboard", headers=_headers(2)).status_code == 403
    assert client.get(f"{ROTA}/{desafio_id}/leaderboard", headers=_headers(3)).status_code == 403


def test_nutricionista_nao_acessa_desafios(client: TestClient, db: Session) -> None:
    factories.criar_nutricionista(db, 10)
    token, _ = criar_token_acesso(10, "nutricionista")
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get(ROTA, headers=headers).status_code == 403
    assert client.get(f"{ROTA}/1/leaderboard", headers=headers).status_code == 403
    assert (
        client.post(f"{ROTA}/1/response", headers=headers, json={"aceitar": True}).status_code
        == 403
    )


def test_placar_de_variacao_calorica_ordena_menor_desvio_primeiro(
    client: TestClient, db: Session
) -> None:
    primeiro = factories.criar_paciente(db, 1)
    factories.criar_paciente(db, 2)  # sem meta: fica sem pontuacao, no fim do placar
    factories.criar_paciente(db, 3)
    primeiro.meta_kcal = Decimal("2000")
    db.commit()
    desafio_id = _criar_desafio(client, 1, tipo="variacao_calorica", convidados=[2, 3])
    for paciente_id in (2, 3):
        client.post(
            f"{ROTA}/{desafio_id}/response", headers=_headers(paciente_id), json={"aceitar": True}
        )
    for hora, tipo in enumerate(TipoRefeicao, start=8):
        _criar_refeicao(db, primeiro.id, tipo, hora)

    placar = client.get(f"{ROTA}/{desafio_id}/leaderboard", headers=_headers(1))

    assert placar.status_code == 200, placar.text
    participantes = placar.json()["participantes"]
    assert participantes[0]["paciente_id"] == 1
    # Janela de dois dias locais: |400 - 2000| + |0 - 2000| = 3600 -> 1800 por dia.
    assert participantes[0]["pontuacao"] == 1800
    assert participantes[0]["unidade"] == "kcal/dia (menor vence)"
    assert {p["pontuacao"] for p in participantes[1:]} == {None}


def test_placar_de_sequencia_da_meta(client: TestClient, db: Session) -> None:
    primeiro = factories.criar_paciente(db, 1)
    segundo = factories.criar_paciente(db, 2)
    # Duas refeicoes de 100 kcal: dentro de 30% de uma meta de 200 kcal
    primeiro.meta_kcal = segundo.meta_kcal = Decimal("200")
    db.commit()
    desafio_id = _criar_desafio(client, 1, tipo="sequencia_meta", convidados=[2])
    client.post(f"{ROTA}/{desafio_id}/response", headers=_headers(2), json={"aceitar": True})
    for hora, tipo in enumerate(list(TipoRefeicao)[:2], start=8):
        _criar_refeicao(db, primeiro.id, tipo, hora)

    placar = client.get(f"{ROTA}/{desafio_id}/leaderboard", headers=_headers(2))

    assert placar.status_code == 200, placar.text
    participantes = placar.json()["participantes"]
    assert [p["paciente_id"] for p in participantes] == [1, 2]
    assert participantes[1]["pontuacao"] == 0
    assert {p["unidade"] for p in participantes} == {"dias consecutivos"}
