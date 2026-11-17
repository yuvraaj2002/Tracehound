"""Hypothesis agent: join every specialist's findings into cited candidate root causes."""

from tracehound.agents.hypothesis.agent import HypothesisAgent, HypothesisAnswer
from tracehound.agents.hypothesis.prompt import PROMPT_VERSION

__all__ = ["PROMPT_VERSION", "HypothesisAgent", "HypothesisAnswer"]
