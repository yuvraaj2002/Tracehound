"""Dependency specialist: read in-scope traces and cite the spans that answer triage."""

from tracehound.agents.dependency.agent import DependencyAgent, DependencyAnswer
from tracehound.agents.dependency.prompt import PROMPT_VERSION

__all__ = ["PROMPT_VERSION", "DependencyAgent", "DependencyAnswer"]
