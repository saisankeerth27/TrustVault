from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_application_imports() -> None:
    assert app.title == "TrustVault API"
    assert app.version == "0.1.0"


def test_health_returns_documented_response() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "TrustVault API",
        "version": "0.1.0",
    }


def test_health_does_not_expose_configuration() -> None:
    response = client.get("/health")
    body = response.text.lower()

    assert set(response.json().keys()) == {"status", "service", "version"}

    for marker in (
        "database",
        "password",
        "secret",
        "jwt",
        "supabase",
        "service_role",
        "cors_allowed_origins",
    ):
        assert marker not in body


def test_unknown_route_returns_consistent_error() -> None:
    response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    payload = response.json()
    assert payload["error"]["code"] == "not_found"
    assert payload["error"]["message"] == "Not Found"


def test_openapi_documentation_is_available() -> None:
    schema_response = client.get("/openapi.json")
    docs_response = client.get("/docs")

    assert schema_response.status_code == 200
    assert schema_response.json()["info"]["title"] == "TrustVault API"
    assert docs_response.status_code == 200
