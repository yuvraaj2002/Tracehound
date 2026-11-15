"""The base class every trace backend adapter extends."""

from tracehound.schemas.traces import Span
from tracehound.tools.source import Source


class TraceSource(Source[Span]):
    """Fetches spans from one backend and returns them as canonical ``Span``s.

    ``fetch`` returns spans from ``services`` with ``start <= span.start <= end``, oldest first.
    """
