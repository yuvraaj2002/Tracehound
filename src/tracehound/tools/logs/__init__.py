"""Log sources: one adapter per backend, all returning ``LogLine``."""

from tracehound.tools.logs.adapters.file import FileLogSource
from tracehound.tools.logs.adapters.loki import LokiLogSource
from tracehound.tools.logs.base import LogSource
from tracehound.tools.logs.dedupe import dedupe_by_message

__all__ = ["FileLogSource", "LogSource", "LokiLogSource", "dedupe_by_message"]
