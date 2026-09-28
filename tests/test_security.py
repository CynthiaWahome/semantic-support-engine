"""Verify authentication at the HTTP boundary using synthetic keys and answers."""

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.core.knowledge_base import get_knowledge_base_service
from app.main import create_app
from app.schemas.knowledge_base import AnswerResponse


@pytest.fixture
def protected_client(monkeypatch):
    """Provide an API with a synthetic key and an observable answering service."""
    monkeypatch.setenv("KB_API_KEY", "synthetic-test-key")
    service = Mock()
    service.answer.return_value = AnswerResponse(
        answer="Synthetic answer", source="knowledge_base"
    )
    app = create_app()
    app.dependency_overrides[get_knowledge_base_service] = lambda: service
    with TestClient(app) as client:
        yield client, service


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"X-API-Key": ""},
        {"X-API-Key": "incorrect"},
        {"X-API-Key": " synthetic-test-key"},
        {"X-API-Key": "synthetic-test-key "},
        {"X-API-Key": "SYNTHETIC-TEST-KEY"},
        {"X-API-Key": "synthetic-test-key,incorrect"},
        [("X-API-Key", "synthetic-test-key"), ("X-API-Key", "incorrect")],
        [("X-API-Key", "incorrect"), ("X-API-Key", "synthetic-test-key")],
        [("X-API-Key", "synthetic-test-key"), ("X-API-Key", "synthetic-test-key")],
        [(b"X-API-Key", b"\xc3\xa9")],
    ],
)
def test_invalid_credentials_never_reach_answer_service(protected_client, headers):
    """Reject missing, mismatched, Unicode and ambiguous header representations."""
    client, service = protected_client
    response = client.post(
        "/knowledge-base/answer", headers=headers, json={"question": "help"}
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing API key"}
    service.answer.assert_not_called()


@pytest.mark.parametrize("configured", [None, "", " ", " key", "key "])
def test_unconfigured_authentication_fails_closed(
    protected_client, monkeypatch, configured
):
    """Never allow anonymous access because server configuration is absent or invalid."""
    client, service = protected_client
    if configured is None:
        monkeypatch.delenv("KB_API_KEY", raising=False)
    else:
        monkeypatch.setenv("KB_API_KEY", configured)
    for headers in [{}, {"X-API-Key": "synthetic-test-key"}]:
        response = client.post(
            "/knowledge-base/answer", headers=headers, json={"question": "help"}
        )
        assert response.status_code == 503
    service.answer.assert_not_called()
    assert client.get("/health").status_code == 200
    assert client.get("/docs").status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "/knowledge-base/answer",
        "/knowledge-base/answer/",
        "/knowledge-base/%61nswer",
    ],
)
def test_routed_path_variants_require_authentication(protected_client, path):
    """Enforce authentication after routing, including redirects and encoded paths."""
    client, service = protected_client
    assert client.post(path, json={"question": "help"}).status_code == 401
    service.answer.assert_not_called()
    response = client.post(
        path, headers={"X-API-Key": "synthetic-test-key"}, json={"question": "help"}
    )
    assert response.status_code == 200
    assert response.json() == {"answer": "Synthetic answer", "source": "knowledge_base"}
    service.answer.assert_called_once_with("help")


def test_query_body_and_cookie_are_not_credentials(protected_client):
    """Accept credentials only from the documented header, never alternate sources."""
    client, service = protected_client
    client.cookies.set("X-API-Key", "synthetic-test-key")
    response = client.post(
        "/knowledge-base/answer?X-API-Key=synthetic-test-key",
        json={"question": "help", "X-API-Key": "synthetic-test-key"},
    )
    assert response.status_code == 401
    service.answer.assert_not_called()


def test_openapi_exposes_authorization_and_public_health(protected_client):
    """Make Swagger authorization usable without protecting liveness or metadata."""
    client, _ = protected_client
    schema = client.get("/openapi.json").json()
    assert schema["paths"]["/knowledge-base/answer"]["post"]["security"] == [
        {"APIKeyHeader": []}
    ]
    assert schema["components"]["securitySchemes"]["APIKeyHeader"] == {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
    }
    assert not schema["paths"]["/health"]["get"].get("security")
    assert client.get("/health").json() == {"status": "ok"}
