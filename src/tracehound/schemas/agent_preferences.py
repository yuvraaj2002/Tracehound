"""Contracts for each user's per-agent model choices."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict

AgentId = Literal["triage", "logs", "metrics", "dependency", "deploy", "hypothesis"]

NOT_CONFIGURED_MESSAGE = (
    "The models for your agents are not configured yet. Choose a model for each agent "
    "before starting an investigation."
)


class AgentModelChoice(BaseModel):
    """The model an agent runs on."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str
    model: str


class AgentModelPreferences(BaseModel):
    """The effective choice for every agent: the user's own, or the default if they never set one.

    `defaults` is what each agent uses until the user picks one, and `customized` lists the agents
    they have chosen for, so the UI can mark them and offer a reset.

    `configured` is false until the user has chosen a model for at least one agent. Investigations
    can't start until then, and `message` says so in words a client can show as it is.
    """

    agents: dict[AgentId, AgentModelChoice]
    defaults: dict[AgentId, AgentModelChoice]
    customized: list[AgentId]
    configured: bool
    message: str | None
    updated_at: AwareDatetime | None
