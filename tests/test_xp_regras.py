"""Regras internas de XP (RF16): refeicao, foto, boas-vindas e limite por tipo/dia."""

from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.tempo import FUSO
from app.models.historico_xp import HistoricoXP
from app.models.paciente import Paciente
from app.services.gamificacao import XP_BOAS_VINDAS, XP_REFEICAO, XP_REFEICAO_FOTO
from tests import factories

ROTA = "/api/v1/refeicoes"


def _ontem(hora: int) -> datetime:
    return (datetime.now(FUSO) - timedelta(days=1)).replace(
        hour=hora, minute=0, second=0, microsecond=0
    )


def _xp(db: Session, paciente_id: int) -> int:
    db.expire_all()
    return db.get(Paciente, paciente_id).xp


def test_cadastro_ganha_bonus_de_boas_vindas(client: TestClient, db: Session) -> None:
    resposta = client.post("/api/v1/auth/cadastro/paciente", json=factories.cadastro())
    assert resposta.status_code == 201, resposta.text
    paciente_id = resposta.json()["usuario"]["id"]

    assert _xp(db, paciente_id) == XP_BOAS_VINDAS
    motivos = [h.motivo for h in db.query(HistoricoXP).filter_by(paciente_id=paciente_id)]
    assert motivos == ["boas_vindas"]


def test_refeicao_rende_xp_uma_vez_por_tipo_por_dia(client: TestClient, db: Session) -> None:
    factories.criar_paciente(db, 1)
    headers = factories.headers_de(1)

    for minuto in (0, 30):  # dois almocos no mesmo dia: so o primeiro pontua
        corpo = factories.refeicao(1, _ontem(12).replace(minute=minuto), tipo="almoco")
        assert client.post(ROTA, json=corpo, headers=headers).status_code == 201
    assert _xp(db, 1) == XP_REFEICAO

    jantar = factories.refeicao(1, _ontem(19), tipo="jantar")
    client.post(ROTA, json=jantar, headers=headers)
    assert _xp(db, 1) == 2 * XP_REFEICAO


def test_refeicao_por_foto_rende_mais(client: TestClient, db: Session) -> None:
    factories.criar_paciente(db, 1)
    corpo = {**factories.refeicao(1, _ontem(12), tipo="almoco"), "origem": "foto"}

    assert client.post(ROTA, json=corpo, headers=factories.headers_de(1)).status_code == 201

    assert _xp(db, 1) == XP_REFEICAO_FOTO


def test_lote_offline_pontua_so_as_refeicoes_novas(client: TestClient, db: Session) -> None:
    factories.criar_paciente(db, 1)
    headers = factories.headers_de(1)
    lote = {
        "paciente_id": 1,
        "refeicoes": [
            factories.refeicao(1, _ontem(8), tipo="cafe_da_manha"),
            factories.refeicao(1, _ontem(12), tipo="almoco"),
        ],
    }

    assert client.post(f"{ROTA}/batch", json=lote, headers=headers).status_code in (200, 201)
    assert _xp(db, 1) == 2 * XP_REFEICAO
    # Reenvio do mesmo lote (deduplicado): nao pontua de novo
    client.post(f"{ROTA}/batch", json=lote, headers=headers)
    assert _xp(db, 1) == 2 * XP_REFEICAO


def test_xp_de_refeicao_entra_no_ranking_semanal(client: TestClient, db: Session) -> None:
    factories.criar_paciente(db, 1)
    headers = factories.headers_de(1)
    client.post(ROTA, json=factories.refeicao(1, tipo="lanche"), headers=headers)

    ranking = client.get("/api/v1/gamificacao/leaderboard", headers=headers).json()

    assert ranking["ranking"][0]["xp_semanal"] == XP_REFEICAO
