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
