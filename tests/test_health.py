"""Verify the public liveness contract."""

from fastapi.testclient import TestClient

from app.main import create_app


def test_health_returns_ok_without_external_services():
    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_is_registered_in_openapi():
    with TestClient(create_app()) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    specification = response.json()
    schema = specification["paths"]["/health"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    assert schema["$ref"] == "#/components/schemas/HealthResponse"
    health_schema = specification["components"]["schemas"]["HealthResponse"]
    assert health_schema["properties"]["status"]["const"] == "ok"
