"""Logs specialist: read the in-scope log lines and cite the ones that answer triage's question."""

from tracehound.agents.logs.agent import LogsAgent, LogsAnswer
from tracehound.agents.logs.prompt import PROMPT_VERSION

__all__ = ["PROMPT_VERSION", "LogsAgent", "LogsAnswer"]
