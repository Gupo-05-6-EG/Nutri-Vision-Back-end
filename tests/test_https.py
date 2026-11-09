"""Testes do modo HTTPS_ONLY: redirect para https e HSTS (Task 1.6, RNF06)."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app

HEALTH = "/api/v1/health"


def _cliente(monkeypatch: pytest.MonkeyPatch, https_only: bool) -> TestClient:
    monkeypatch.setattr(get_settings(), "HTTPS_ONLY", https_only)
    return TestClient(create_app(), follow_redirects=False)


def test_desligado_por_padrao_nao_redireciona(monkeypatch: pytest.MonkeyPatch) -> None:
    assert get_settings().HTTPS_ONLY is False
    resposta = _cliente(monkeypatch, False).get("http://testserver" + HEALTH)

    assert resposta.status_code == 200
    assert "strict-transport-security" not in resposta.headers


def test_http_e_redirecionado_para_https(monkeypatch: pytest.MonkeyPatch) -> None:
    resposta = _cliente(monkeypatch, True).get("http://testserver" + HEALTH)

    assert resposta.status_code == 307
    assert resposta.headers["location"] == "https://testserver" + HEALTH


def test_https_responde_com_hsts(monkeypatch: pytest.MonkeyPatch) -> None:
    resposta = _cliente(monkeypatch, True).get("https://testserver" + HEALTH)

    assert resposta.status_code == 200
    assert "max-age=31536000" in resposta.headers["strict-transport-security"]
