from fastapi.testclient import TestClient


def test_root_responde(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "docs" in resp.json()


def test_health_liveness(client: TestClient) -> None:
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_health_readiness_consulta_o_banco(client: TestClient) -> None:
    resp = client.get("/api/v1/health/db")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "database": "up"}


def test_openapi_disponivel(client: TestClient) -> None:
    resp = client.get("/api/v1/openapi.json")
    assert resp.status_code == 200
    assert resp.json()["info"]["version"] == "0.1.0"
