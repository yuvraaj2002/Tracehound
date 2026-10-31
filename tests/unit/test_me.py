import pytest
from fastapi.testclient import TestClient

from tests.unit.test_api_keys import USER_ID, VERIFIER, _auth, _token
from tracehound.api.app import create_app
from tracehound.api.dependencies import get_token_verifier


@pytest.fixture
def client() -> TestClient:
    app = create_app(pool_factory=lambda: pytest.fail("pool should not open"))
    app.dependency_overrides[get_token_verifier] = lambda: VERIFIER
    return TestClient(app)


def test_returns_the_token_owner(client: TestClient) -> None:
    token = _token(
        user_metadata={"full_name": "Ada Lovelace", "avatar_url": "https://example.com/a.png"}
    )
    response = client.get("/v1/me", headers=_auth(token))
    assert response.status_code == 200
    assert response.json() == {
        "id": str(USER_ID),
        "email": "dev@example.com",
        "name": "Ada Lovelace",
        "avatar_url": "https://example.com/a.png",
    }


def test_falls_back_to_github_login(client: TestClient) -> None:
    token = _token(user_metadata={"user_name": "ada"})
    assert client.get("/v1/me", headers=_auth(token)).json()["name"] == "ada"


def test_without_metadata_name_is_null(client: TestClient) -> None:
    body = client.get("/v1/me", headers=_auth()).json()
    assert (body["name"], body["avatar_url"]) == (None, None)


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer not-a-jwt"}])
def test_unauthenticated_is_401(client: TestClient, headers: dict[str, str]) -> None:
    response = client.get("/v1/me", headers=headers)
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
