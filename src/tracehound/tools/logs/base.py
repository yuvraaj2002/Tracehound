"""The base class every log backend adapter extends."""

from tracehound.schemas.logs import LogLine
from tracehound.tools.source import Source


class LogSource(Source[LogLine]):
    """Fetches log lines from one backend and returns them as canonical ``LogLine``s.

    ``fetch`` returns lines from ``services`` with ``start <= timestamp <= end``, oldest first.
    """
