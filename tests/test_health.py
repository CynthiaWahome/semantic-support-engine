"""Verify the public liveness contract."""

from fastapi.testclient import TestClient

from app.main import create_app


def test_health_returns_ok_without_external_services():
    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
