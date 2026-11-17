"""Triage: decide which services, time ranges and specialist questions an investigation covers."""

from tracehound.agents.triage.agent import TriageAgent, TriageDecision
from tracehound.agents.triage.prompt import PROMPT_VERSION

__all__ = ["PROMPT_VERSION", "TriageAgent", "TriageDecision"]
