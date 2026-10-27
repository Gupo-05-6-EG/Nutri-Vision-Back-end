"""Testes de logs, request id e readiness (Task 7.1, RNF09)."""

import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.core.observabilidade import FormatoJson
from app.db.session import get_db

ROTA = "/api/v1/health"


def _acessos(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == "nutrivision.acesso"]


def test_gera_request_id_e_devolve_no_header(client: TestClient) -> None:
    resposta = client.get(ROTA)

    rid = resposta.headers["x-request-id"]
    assert len(rid) == 32
    assert client.get(ROTA).headers["x-request-id"] != rid


def test_reaproveita_request_id_do_cliente(client: TestClient) -> None:
    resposta = client.get(ROTA, headers={"X-Request-ID": "app-123"})

    assert resposta.headers["x-request-id"] == "app-123"


def test_loga_um_acesso_por_requisicao(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="nutrivision.acesso")

    client.get("/api/v1/refeicoes/999", headers={"X-Request-ID": "r-1"})

    (acesso,) = _acessos(caplog)
    assert acesso.metodo == "GET"
    assert acesso.caminho == "/api/v1/refeicoes/999"
    assert acesso.status == 404
    assert acesso.duracao_ms >= 0


def test_formato_json_inclui_campos_extras() -> None:
    record = logging.makeLogRecord(
        {"name": "nutrivision.acesso", "levelname": "INFO", "msg": "GET / 200", "status": 200}
    )
    record.request_id = "r-9"

    evento = json.loads(FormatoJson().format(record))

    assert evento["msg"] == "GET / 200"
    assert evento["status"] == 200
    assert evento["request_id"] == "r-9"
    assert evento["ts"].endswith("+00:00")


def test_readiness_responde_503_sem_banco(app: FastAPI) -> None:
    class _BancoFora:
        def execute(self, *_args, **_kwargs):
            raise OperationalError("SELECT 1", {}, Exception("conexao recusada"))

    app.dependency_overrides[get_db] = lambda: _BancoFora()
    with TestClient(app) as client:
        resposta = client.get("/api/v1/health/db")

    assert resposta.status_code == 503
    assert resposta.json()["detail"] == "Banco indisponivel"
