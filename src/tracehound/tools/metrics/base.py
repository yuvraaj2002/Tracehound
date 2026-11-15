"""The base class every metric backend adapter extends."""

from tracehound.schemas.metrics import MetricSeries
from tracehound.tools.source import Source


class MetricSource(Source[MetricSeries]):
    """Fetches time series from one backend and returns them as canonical ``MetricSeries``.

    ``fetch`` returns series from ``services`` with points where ``start <= timestamp <= end``.
    Series with no points in the window are dropped.
    """
