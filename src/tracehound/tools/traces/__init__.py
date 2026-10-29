"""Trace sources: one adapter per backend, all returning ``Span``."""

from tracehound.tools.traces.adapters.file import FileTraceSource
from tracehound.tools.traces.adapters.tempo import TempoTraceSource
from tracehound.tools.traces.base import TraceSource

__all__ = ["FileTraceSource", "TempoTraceSource", "TraceSource"]
