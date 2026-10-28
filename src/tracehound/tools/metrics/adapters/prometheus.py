"""Metric source for Prometheus: PromQL range queries over HTTP, mapped to ``MetricSeries``."""

import hashlib
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from string import Template
from typing import Any

import httpx

from tracehound.schemas.telemetry import MetricPoint, MetricSeries
from tracehound.tools.metrics.base import MetricSource


@dataclass(frozen=True)
class MetricQuery:
    """One named PromQL query, run once per ``fetch``.

    ``promql`` is a ``string.Template``: ``$selector`` becomes the service matcher and ``$label``
    the service label name. The query must keep that label on every result series, usually with
    ``sum by ($label) (...)``, so each series can be assigned to a service.
    """

    name: str
    unit: str
    promql: str


# RED metrics from the OpenTelemetry HTTP server histogram, as Prometheus names it.
_DURATION = "http_server_request_duration_seconds"
DEFAULT_QUERIES = (
    MetricQuery(
        name="http_request_rate",
        unit="req/s",
        promql=f"sum by ($label) (rate({_DURATION}_count{{$selector}}[5m]))",
    ),
    MetricQuery(
        name="http_5xx_rate",
        unit="ratio",
        promql=(
            f"sum by ($label) (rate({_DURATION}_count"
            "{$selector, http_response_status_code=~`5..`}[5m]))"
            f" / sum by ($label) (rate({_DURATION}_count{{$selector}}[5m]))"
        ),
    ),
    MetricQuery(
        name="http_p95_latency_ms",
        unit="ms",
        promql=(
            "1000 * histogram_quantile(0.95, "
            f"sum by ($label, le) (rate({_DURATION}_bucket{{$selector}}[5m])))"
        ),
    ),
)


class PrometheusMetricSource(MetricSource):
    """Reads series from Prometheus's ``/api/v1/query_range``, one request per ``MetricQuery``.

    Works with anything that serves the Prometheus HTTP API (Mimir, Thanos, Cortex,
    VictoriaMetrics). Services are matched on one label (``job`` by default, which Prometheus
    sets from OpenTelemetry's ``service.name`` on OTLP ingest). Prometheus has no series IDs or
    units, so each series gets a stable ID hashed from its query name and labels, and its unit
    comes from the query. NaN and infinite samples, such as a ratio with no traffic, are dropped.
    """

    def __init__(
        self,
        client: httpx.Client,
        queries: tuple[MetricQuery, ...] = DEFAULT_QUERIES,
        service_label: str = "job",
        step: timedelta = timedelta(minutes=1),
    ) -> None:
        self._client = client  # base_url, auth headers and tenant (X-Scope-OrgID) set by caller
        self._queries = queries
        self._service_label = service_label
        self._step = step

    def fetch(self, services: set[str], start: datetime, end: datetime) -> list[MetricSeries]:
        """Series from ``services`` with points where ``start <= timestamp <= end``.

        Series with no points in the window are dropped. Raises ``ValueError`` if a result
        series lacks the service label or Prometheus returns an error.
        """
        if not services:
            return []
        result = []
        for query in self._queries:
            for raw in self._query_range(self._promql(query, services), start, end):
                series = self._to_series(query, raw)
                if series.points:
                    result.append(series)
        return sorted(result, key=lambda s: (s.service, s.name, s.id))

    def _promql(self, query: MetricQuery, services: set[str]) -> str:
        # Backtick strings are raw in PromQL, so only regex metacharacters need escaping.
        names = "|".join(re.escape(s) for s in sorted(services))
        selector = f"{self._service_label}=~`{names}`"
        return Template(query.promql).substitute(selector=selector, label=self._service_label)

    def _query_range(self, promql: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
        response = self._client.get(
            "/api/v1/query_range",
            params={
                "query": promql,
                "start": start.timestamp(),
                "end": end.timestamp(),  # inclusive, unlike Loki
                "step": self._step.total_seconds(),
            },
        )
        response.raise_for_status()
        body = response.json()
        if body.get("status") != "success" or body["data"]["resultType"] != "matrix":
            raise ValueError(f"unexpected Prometheus response: {str(body)[:200]}")
        return body["data"]["result"]

    def _to_series(self, query: MetricQuery, raw: dict[str, Any]) -> MetricSeries:
        labels: dict[str, str] = raw["metric"]
        if self._service_label not in labels:
            raise ValueError(
                f"query {query.name!r} returned a series without {self._service_label!r}; "
                f"group by it: {labels}"
            )
        digest = hashlib.sha256(f"{query.name}|{sorted(labels.items())}".encode()).hexdigest()
        return MetricSeries(
            id=f"prom-{digest[:16]}",
            service=labels[self._service_label],
            name=query.name,
            unit=query.unit,
            points=[
                MetricPoint(timestamp=datetime.fromtimestamp(float(ts), tz=UTC), value=value)
                for ts, text in raw["values"]
                if math.isfinite(value := float(text))
            ],
        )
