from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from tests.unit.test_api_keys import VERIFIER, _auth
from tracehound.api.app import create_app
from tracehound.api.dependencies import get_agent_model_store, get_token_verifier
from tracehound.helpers.agent_model_helper import (
    AgentModelStore,
    InvalidModelChoice,
    default_choice,
    validate_choice,
)
from tracehound.helpers.model_config_helper import allowed_models, load_model_config
from tracehound.schemas import AgentModelChoice, AgentModelPreferences
from tracehound.schemas.agent_preferences import NOT_CONFIGURED_MESSAGE

GEMMA = "google/gemma-4-26b-a4b-it:free"
BODY = {"provider": "google", "model": GEMMA}


class FakeStore:
    """Stands in for the database-backed store: keeps choices in memory."""

    def __init__(self) -> None:
        self.saved: dict[str, AgentModelChoice] = {}

    def get(self, user_id: object) -> AgentModelPreferences:
        agents = {a: default_choice(a) for a in load_model_config()["agent_defaults"]}
        agents.update(self.saved)
        return AgentModelPreferences(
            agents=agents,
            defaults={a: default_choice(a) for a in load_model_config()["agent_defaults"]},
            customized=list(self.saved),
            configured=bool(self.saved),
            message=None if self.saved else NOT_CONFIGURED_MESSAGE,
            updated_at=datetime.now(UTC) if self.saved else None,
        )

    def put(self, user_id: object, agent: str, choice: AgentModelChoice) -> AgentModelPreferences:
        validate_choice(choice)
        self.saved[agent] = choice
        return self.get(user_id)


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture
def client(store: FakeStore) -> TestClient:
    app = create_app(engine_factory=lambda: pytest.fail("engine should not be created"))
    app.dependency_overrides[get_token_verifier] = lambda: VERIFIER
    app.dependency_overrides[get_agent_model_store] = lambda: store
    return TestClient(app)


def test_every_agent_default_is_an_allowed_model() -> None:
    defaults = load_model_config()["agent_defaults"]
    assert set(defaults) == {"triage", "logs", "metrics", "dependency", "deploy", "hypothesis"}
    for agent in defaults:
        choice = default_choice(agent)
        assert choice.model in allowed_models()
        validate_choice(choice)


def test_get_returns_defaults_for_a_new_user(client: TestClient) -> None:
    body = client.get("/v1/agent-models/preferences", headers=_auth()).json()
    assert body["customized"] == []
    assert body["updated_at"] is None
    assert body["defaults"] == body["agents"]
    assert body["configured"] is False
    assert "not configured" in body["message"]
    assert set(body["agents"]) == {
        "triage",
        "logs",
        "metrics",
        "dependency",
        "deploy",
        "hypothesis",
    }


def test_put_saves_one_agent_and_leaves_the_rest(client: TestClient) -> None:
    response = client.put("/v1/agent-models/preferences/logs", json=BODY, headers=_auth())
    assert response.status_code == 200
    body = response.json()
    assert body["agents"]["logs"] == BODY
    assert body["customized"] == ["logs"]
    assert body["configured"] is True and body["message"] is None
    assert body["agents"]["metrics"] == default_choice("metrics").model_dump()


@pytest.mark.parametrize(
    "body",
    [
        {**BODY, "model": "openai/gpt-5"},  # not a model we offer
        {**BODY, "provider": "nvidia"},  # provider doesn't offer that model
    ],
)
def test_put_rejects_models_we_do_not_offer(client: TestClient, body: dict[str, str]) -> None:
    response = client.put("/v1/agent-models/preferences/logs", json=body, headers=_auth())
    assert response.status_code == 422


@pytest.mark.parametrize(
    "path,body",
    [
        ("/v1/agent-models/preferences/janitor", BODY),  # unknown agent
        ("/v1/agent-models/preferences/logs", {**BODY, "creativity": "balanced"}),  # removed field
        ("/v1/agent-models/preferences/logs", {**BODY, "extra": 1}),
        ("/v1/agent-models/preferences/logs", {"provider": "google"}),
    ],
)
def test_put_rejects_malformed_requests(client: TestClient, path: str, body: dict) -> None:
    assert client.put(path, json=body, headers=_auth()).status_code == 422


def test_requires_authentication(client: TestClient) -> None:
    assert client.get("/v1/agent-models/preferences").status_code == 401
    assert client.put("/v1/agent-models/preferences/logs", json=BODY).status_code == 401


def test_validate_choice_messages() -> None:
    with pytest.raises(InvalidModelChoice, match="not a model Tracehound offers"):
        validate_choice(AgentModelChoice(provider="x", model="x/y"))


def test_a_stored_model_that_is_no_longer_offered_is_ignored() -> None:
    assert AgentModelStore._stored_choice({**BODY, "model": "google/retired"}) is None
    assert AgentModelStore._stored_choice({"garbage": True}) is None
    assert AgentModelStore._stored_choice(BODY) == AgentModelChoice(**BODY)


def test_has_configuration_needs_a_valid_saved_choice() -> None:
    class Rows:
        def __init__(self, config: dict) -> None:
            self.row = type("Row", (), {"config": config})()

        def __call__(self):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def scalar(self, _stmt: object) -> object:
            return self.row

    from uuid import uuid4

    uid = uuid4()
    assert AgentModelStore(Rows({"agents": {"logs": BODY}})).has_configuration(uid) is True
    assert AgentModelStore(Rows({})).has_configuration(uid) is False
    assert AgentModelStore(Rows({"agents": {}})).has_configuration(uid) is False
    retired = {"agents": {"logs": {**BODY, "model": "google/retired"}}}
    assert AgentModelStore(Rows(retired)).has_configuration(uid) is False
