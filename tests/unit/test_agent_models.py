import pytest
from fastapi.testclient import TestClient

from tests.unit.test_api_keys import VERIFIER, _auth
from tracehound.api.app import create_app
from tracehound.api.dependencies import get_token_verifier
from tracehound.helpers.model_config_helper import allowed_models


@pytest.fixture
def client() -> TestClient:
    app = create_app(engine_factory=lambda: pytest.fail("engine should not be created"))
    app.dependency_overrides[get_token_verifier] = lambda: VERIFIER
    return TestClient(app)


def test_lists_every_configured_model(client: TestClient) -> None:
    response = client.get("/v1/agent-models/providers", headers=_auth())
    assert response.status_code == 200
    body = response.json()
    assert [m for p in body["providers"] for m in p["models"]] == allowed_models()
    assert body["default"]["model"] in allowed_models()


def test_requires_authentication(client: TestClient) -> None:
    assert client.get("/v1/agent-models/providers").status_code == 401


from tracehound.helpers.model_directory import (  # noqa: E402
    ModelDirectory,
    ModelDirectoryUnavailable,
    get_model_directory,
)

GEMMA = "google/gemma-4-26b-a4b-it:free"
LISTING = [
    {
        "id": GEMMA,
        "name": "Google: Gemma 4 26B A4B (free)",
        "description": "An open model.",
        "created": 1_750_000_000,
        "context_length": 262144,
        "architecture": {"input_modalities": ["text", "image"], "output_modalities": ["text"]},
        "pricing": {"prompt": "0", "completion": "0"},
        "top_provider": {"max_completion_tokens": 32768, "is_moderated": False},
        "supported_parameters": ["tools", "temperature", "reasoning"],
    }
]


def _client_with(fetch) -> TestClient:
    app = create_app(engine_factory=lambda: pytest.fail("engine should not be created"))
    app.dependency_overrides[get_token_verifier] = lambda: VERIFIER
    directory = ModelDirectory(fetch)
    app.dependency_overrides[get_model_directory] = lambda: directory
    return TestClient(app)


def test_model_details_have_no_pricing() -> None:
    client = _client_with(lambda: LISTING)
    response = client.get(f"/v1/agent-models/models/{GEMMA}", headers=_auth())
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Gemma 4 26B A4B"
    assert body["context_length"] == 262144
    assert body["max_output_tokens"] == 32768
    assert body["input_modalities"] == ["text", "image"]
    assert (body["supports_tools"], body["supports_reasoning"]) == (True, True)
    assert body["supports_structured_output"] is False
    assert "pricing" not in body and "prompt" not in str(body)


def test_model_not_listed_upstream_still_returns_basics() -> None:
    body = _client_with(lambda: []).get(f"/v1/agent-models/models/{GEMMA}", headers=_auth()).json()
    assert (body["listed"], body["context_length"], body["provider_label"]) == (
        False,
        None,
        "Google",
    )


def test_unknown_model_is_404() -> None:
    client = _client_with(lambda: LISTING)
    assert client.get("/v1/agent-models/models/openai/gpt-5", headers=_auth()).status_code == 404


def test_upstream_failure_is_502() -> None:
    def broken() -> list[dict]:
        raise ModelDirectoryUnavailable("down")

    assert (
        _client_with(broken).get(f"/v1/agent-models/models/{GEMMA}", headers=_auth()).status_code
        == 502
    )


def test_model_details_require_authentication() -> None:
    assert _client_with(lambda: LISTING).get(f"/v1/agent-models/models/{GEMMA}").status_code == 401


def test_catalog_returns_every_model_with_details() -> None:
    client = _client_with(lambda: LISTING)
    response = client.get("/v1/agent-models/catalog", headers=_auth())
    assert response.status_code == 200
    body = response.json()
    models = [m for p in body["providers"] for m in p["models"]]
    assert [m["id"] for m in models] == allowed_models()
    gemma = next(m for m in models if m["id"] == GEMMA)
    assert (gemma["listed"], gemma["context_length"]) == (True, 262144)
    assert next(m for m in models if m["id"] != GEMMA)["listed"] is False
    assert body["default"]["model"] in allowed_models()
    assert "pricing" not in str(body)


def test_catalog_requires_authentication() -> None:
    assert _client_with(lambda: LISTING).get("/v1/agent-models/catalog").status_code == 401
