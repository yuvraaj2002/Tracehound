import time
from datetime import UTC, datetime
from uuid import UUID, uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from tracehound.api.app import create_app
from tracehound.api.dependencies import get_api_key_management, get_token_verifier
from tracehound.auth import InvalidToken, TokenVerifier
from tracehound.helpers.api_key_helper import ApiKeyLimitReached, ApiKeyManagement
from tracehound.schemas import ApiKeyCreated, ApiKeySummary

ISSUER = "https://project.supabase.co/auth/v1"
USER_ID = uuid4()
SIGNING_KEY = ec.generate_private_key(ec.SECP256R1())


class LocalKeys:
    """Serves the test keypair's public key, standing in for the project's JWKS endpoint."""

    def get_signing_key_from_jwt(self, token: str) -> jwt.PyJWK:
        return jwt.PyJWK.from_dict(
            jwt.algorithms.ECAlgorithm.to_jwk(SIGNING_KEY.public_key(), as_dict=True), "ES256"
        )


def _token(**overrides: object) -> str:
    claims = {
        "sub": str(USER_ID),
        "aud": "authenticated",
        "iss": ISSUER,
        "exp": int(time.time()) + 300,
        "email": "dev@example.com",
        **overrides,
    }
    return jwt.encode(claims, SIGNING_KEY, algorithm="ES256")


VERIFIER = TokenVerifier(ISSUER, LocalKeys())


class MemoryKeys:
    """In-memory stand-in for `ApiKeyManagement`, so these tests need no database."""

    def __init__(self) -> None:
        self.created: list[tuple[UUID, ApiKeyCreated]] = []

    def create(self, user_id: UUID, name: str) -> ApiKeyCreated:
        raw_key = ApiKeyManagement.generate_raw_key()
        prefix, suffix = ApiKeyManagement.display_parts(raw_key)
        created = ApiKeyCreated(
            id=uuid4(),
            name=name,
            key=raw_key,
            prefix=prefix,
            suffix=suffix,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self.created.append((user_id, created))
        return created

    def rename(self, user_id: UUID, key_id: UUID, new_name: str) -> ApiKeySummary | None:
        for owner, key in self.created:
            if owner == user_id and key.id == key_id:
                key.name = new_name
                key.updated_at = datetime.now(UTC)
                return ApiKeySummary(**key.model_dump(exclude={"key"}))
        return None


class BrokenKeys:
    def create(self, user_id: UUID, name: str) -> ApiKeyCreated:
        raise OperationalError("SELECT 1", None, Exception("connection lost"))


def _app_with(keys: object) -> FastAPI:
    app = create_app(engine_factory=lambda: pytest.fail("engine should not be created"))
    app.dependency_overrides[get_api_key_management] = lambda: keys
    app.dependency_overrides[get_token_verifier] = lambda: VERIFIER
    return app


@pytest.fixture
def keys() -> MemoryKeys:
    return MemoryKeys()


@pytest.fixture
def client(keys: MemoryKeys) -> TestClient:
    return TestClient(_app_with(keys))


def _auth(token: str | None = None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token or _token()}"}


# Token verification


def test_valid_token_resolves_user() -> None:
    user = VERIFIER.verify(_token())
    assert user.user_id == USER_ID
    assert user.email == "dev@example.com"


@pytest.mark.parametrize(
    "overrides",
    [
        {"exp": int(time.time()) - 10},
        {"aud": "anon"},
        {"iss": "https://other.supabase.co/auth/v1"},
        {"sub": "not-a-uuid"},
    ],
)
def test_rejects_bad_claims(overrides: dict[str, object]) -> None:
    with pytest.raises(InvalidToken):
        VERIFIER.verify(_token(**overrides))


def test_rejects_token_signed_by_another_key() -> None:
    other = jwt.encode(
        {"sub": str(USER_ID), "aud": "authenticated", "iss": ISSUER, "exp": time.time() + 300},
        ec.generate_private_key(ec.SECP256R1()),
        algorithm="ES256",
    )
    with pytest.raises(InvalidToken):
        VERIFIER.verify(other)


def test_rejects_hs256_token() -> None:
    forged = jwt.encode({"sub": str(USER_ID)}, "shared-secret", algorithm="HS256")
    with pytest.raises(InvalidToken):
        VERIFIER.verify(forged)


# Key material


def test_raw_key_format() -> None:
    raw_key = ApiKeyManagement.generate_raw_key()
    assert raw_key.startswith("th_")
    assert len(raw_key) == 46  # "th_" + 43 url-safe characters for 32 random bytes
    assert ApiKeyManagement.generate_raw_key() != raw_key


def test_display_parts() -> None:
    prefix, suffix = ApiKeyManagement.display_parts("th_AbCdefghijklmnopWxYz")
    assert (prefix, suffix) == ("th_AbCd", "WxYz")


def test_hash_is_keyed_by_secret() -> None:
    pool = object()  # hashing never touches the database
    first = ApiKeyManagement(pool, "secret-one")  # type: ignore[arg-type]
    second = ApiKeyManagement(pool, "secret-two")  # type: ignore[arg-type]
    assert first.hash_key("th_key") == first.hash_key("th_key")
    assert first.hash_key("th_key") != second.hash_key("th_key")
    assert len(first.hash_key("th_key")) == 64


# POST /v1/api-keys


def test_creates_key_for_signed_in_user(client: TestClient, keys: MemoryKeys) -> None:
    response = client.post("/v1/api-keys", json={"name": "  Alertmanager  "}, headers=_auth())
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Alertmanager"
    assert body["key"].startswith(body["prefix"])
    assert body["key"].endswith(body["suffix"])
    assert keys.created[0][0] == USER_ID


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer nonsense"}])
def test_requires_valid_token(client: TestClient, keys: MemoryKeys, headers: dict) -> None:
    response = client.post("/v1/api-keys", json={"name": "ci"}, headers=headers)
    assert response.status_code == 401
    assert keys.created == []


@pytest.mark.parametrize("payload", [{}, {"name": ""}, {"name": "   "}, {"name": "x" * 101}])
def test_rejects_invalid_name(client: TestClient, payload: dict) -> None:
    assert client.post("/v1/api-keys", json=payload, headers=_auth()).status_code == 422


def test_rejects_unexpected_fields(client: TestClient) -> None:
    payload = {"name": "ci", "user_id": str(uuid4())}
    assert client.post("/v1/api-keys", json=payload, headers=_auth()).status_code == 422


def test_database_error_returns_500() -> None:
    client = TestClient(_app_with(BrokenKeys()))
    response = client.post("/v1/api-keys", json={"name": "ci"}, headers=_auth())
    assert response.status_code == 500
    assert response.json() == {"detail": "Could not create the API key."}


class FullKeys:
    def create(self, user_id: UUID, name: str) -> ApiKeyCreated:
        raise ApiKeyLimitReached(user_id)


def test_sixth_active_key_returns_409() -> None:
    client = TestClient(_app_with(FullKeys()))
    response = client.post("/v1/api-keys", json={"name": "ci"}, headers=_auth())
    assert response.status_code == 409
    assert "5 active API keys" in response.json()["detail"]


def test_renames_own_key(client: TestClient, keys: MemoryKeys) -> None:
    key_id = client.post("/v1/api-keys", json={"name": "ci"}, headers=_auth()).json()["id"]
    response = client.put(
        f"/v1/api-keys/{key_id}", json={"new_name": "  deploy bot "}, headers=_auth()
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "deploy bot"
    assert body["updated_at"] >= body["created_at"]
    assert "key" not in body


def test_rename_unknown_key_returns_404(client: TestClient) -> None:
    response = client.put(f"/v1/api-keys/{uuid4()}", json={"new_name": "x"}, headers=_auth())
    assert response.status_code == 404


@pytest.mark.parametrize(
    "payload", [{}, {"new_name": ""}, {"new_name": "x" * 101}, {"new_name": "a", "x": 1}]
)
def test_rename_rejects_invalid_payload(client: TestClient, payload: dict[str, object]) -> None:
    response = client.put(f"/v1/api-keys/{uuid4()}", json=payload, headers=_auth())
    assert response.status_code == 422


def test_rename_requires_auth(client: TestClient) -> None:
    assert client.put(f"/v1/api-keys/{uuid4()}", json={"new_name": "x"}).status_code == 401
