from fastapi.testclient import TestClient

from app.main import app


def test_health_check_returns_service_metadata() -> None:
    response = TestClient(app).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "AdPilot AI",
        "version": "0.1.0",
        "environment": "local",
    }


def test_openapi_exposes_health_endpoint() -> None:
    response = TestClient(app).get("/openapi.json")

    assert response.status_code == 200
    assert "/api/v1/health" in response.json()["paths"]
