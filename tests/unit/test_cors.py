import pytest
from fastapi.testclient import TestClient

from tracehound.api.app import cors_origins, create_app
from tracehound.api.dependencies import get_incident_helper

UI_ORIGIN = "http://localhost:5173"


def _client() -> TestClient:
    # As in test_incident_api: the lifespan never runs, so no database pool opens.
    app = create_app(pool_factory=lambda: pytest.fail("pool should not open"))
    app.dependency_overrides[get_incident_helper] = lambda: pytest.fail("helper not needed")
    return TestClient(app)


def _preflight(client: TestClient, origin: str):
    return client.options(
        "/v1/incidents",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization, content-type",
        },
    )


def test_preflight_from_allowed_origin_gets_cors_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", UI_ORIGIN)
    response = _preflight(_client(), UI_ORIGIN)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == UI_ORIGIN
    allowed = response.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed
    assert "content-type" in allowed
    assert "POST" in response.headers["access-control-allow-methods"]


def test_preflight_from_other_origin_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", UI_ORIGIN)
    response = _preflight(_client(), "https://evil.example")
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_cors_origins_splits_and_trims(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", " http://localhost:5173, https://app.example.com ,")
    assert cors_origins() == ["http://localhost:5173", "https://app.example.com"]
