"""Each user's model choice per agent, stored in `agent_model_settings`."""

from typing import get_args
from uuid import UUID

from sqlalchemy import func, literal, select
from sqlalchemy.dialects.postgresql import JSONB, insert

from tracehound.db import SessionFactory
from tracehound.helpers.model_config_helper import allowed_models, load_model_config
from tracehound.models import AgentModelSettingsRow
from tracehound.schemas import AgentId, AgentModelChoice, AgentModelPreferences
from tracehound.schemas.agent_preferences import NOT_CONFIGURED_MESSAGE


class InvalidModelChoice(Exception):
    """The choice isn't one we offer. The message is safe to show the user."""


def provider_of(model_id: str) -> str | None:
    """The provider that offers `model_id`, or None when it isn't in the models config."""
    return next(
        (p["id"] for p in load_model_config()["providers"] if model_id in p["models"]), None
    )


def default_choice(agent: AgentId) -> AgentModelChoice:
    entry = load_model_config()["agent_defaults"][agent]
    provider = provider_of(entry["model"])
    assert provider is not None, f"the default model for {agent} is not in the config"
    return AgentModelChoice(provider=provider, model=entry["model"])


def validate_choice(choice: AgentModelChoice) -> None:
    """Raise `InvalidModelChoice` unless the model is offered and belongs to the given provider."""
    if choice.model not in allowed_models():
        raise InvalidModelChoice(f"'{choice.model}' is not a model Tracehound offers.")
    if provider_of(choice.model) != choice.provider:
        raise InvalidModelChoice(f"'{choice.model}' is not offered by '{choice.provider}'.")


class AgentModelStore:
    """Reads and writes a user's choices. Agents the user hasn't changed use the config defaults."""

    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    def get(self, user_id: UUID) -> AgentModelPreferences:
        with self._sessions() as session:
            row = session.scalar(
                select(AgentModelSettingsRow).where(AgentModelSettingsRow.user_id == user_id)
            )
            stored = (row.config.get("agents") or {}) if row else {}
            updated_at = row.updated_at if row else None
        agents: dict[AgentId, AgentModelChoice] = {}
        customized: list[AgentId] = []
        for agent in get_args(AgentId):
            choice = self._stored_choice(stored.get(agent))
            if choice is not None:
                customized.append(agent)
            agents[agent] = choice or default_choice(agent)
        defaults = {agent: default_choice(agent) for agent in get_args(AgentId)}
        return AgentModelPreferences(
            agents=agents,
            defaults=defaults,
            customized=customized,
            configured=bool(customized),
            message=None if customized else NOT_CONFIGURED_MESSAGE,
            updated_at=updated_at,
        )

    def has_configuration(self, user_id: UUID) -> bool:
        """True once the user has saved a model choice for at least one agent."""
        with self._sessions() as session:
            row = session.scalar(
                select(AgentModelSettingsRow).where(AgentModelSettingsRow.user_id == user_id)
            )
            stored = (row.config.get("agents") or {}) if row else {}
        return any(self._stored_choice(raw) is not None for raw in stored.values())

    @staticmethod
    def _stored_choice(raw: object) -> AgentModelChoice | None:
        """A stored choice, or None when it is malformed or names a model we no longer offer."""
        try:
            choice = AgentModelChoice.model_validate(raw)
            validate_choice(choice)
        except (ValueError, InvalidModelChoice):
            return None
        return choice

    def put(self, user_id: UUID, agent: AgentId, choice: AgentModelChoice) -> AgentModelPreferences:
        """Save `choice` for one agent, leaving the user's other agents as they were.

        Raises `InvalidModelChoice` when the model isn't offered or doesn't match the provider.
        """
        validate_choice(choice)
        column = AgentModelSettingsRow.config
        new = {"agents": {agent: choice.model_dump()}}
        stmt = insert(AgentModelSettingsRow).values(user_id=user_id, config=new)
        # jsonb_set can't create a missing parent key, so make sure `agents` exists first.
        with_agents = func.jsonb_set(
            column,
            ["agents"],
            func.coalesce(column["agents"], func.cast(literal("{}"), JSONB)),
            True,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[AgentModelSettingsRow.user_id],
            set_={
                "config": func.jsonb_set(
                    with_agents, ["agents", agent], stmt.excluded.config["agents"][agent], True
                ),
                "updated_at": func.now(),
            },
        )
        with self._sessions.begin() as session:
            session.execute(stmt)
        return self.get(user_id)
