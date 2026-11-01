"""Dummy checkout service that can run out of database connections on demand.

Each checkout holds a pooled Postgres connection for about 200ms. At 40 requests/second it needs
about 8 connections at once: a pool of 20 copes, a pool of 5 does not. Then requests queue for a
connection, give up after the acquire timeout and return 503, which is the
``checkout_db_pool_exhaustion`` scenario.

Telemetry (logs, traces, metrics) is sent by ``opentelemetry-instrument`` in the Dockerfile.
"""

import logging
import os
import random
import threading
import uuid

from fastapi import FastAPI, HTTPException
from opentelemetry import metrics, trace
from pydantic import BaseModel, Field
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.pool import QueuePool

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://checkout:checkout@localhost:5432/orders"
)
APP_VERSION = os.environ.get("APP_VERSION", "1.13.2")
NORMAL_POOL_SIZE = int(os.environ.get("DB_POOL_SIZE", "20"))
NORMAL_TIMEOUT_S = float(os.environ.get("DB_POOL_TIMEOUT_S", "30"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("checkout-api")
tracer = trace.get_tracer("checkout-api")
meter = metrics.get_meter("checkout-api")


class PoolSettings(BaseModel):
    pool_size: int = Field(ge=1, le=100)
    timeout_s: float = Field(gt=0, le=60)


class Pool:
    """The current engine, swappable at runtime so a fault can shrink the pool."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.settings = PoolSettings(pool_size=NORMAL_POOL_SIZE, timeout_s=NORMAL_TIMEOUT_S)
        self.engine = self._build(self.settings)

    @staticmethod
    def _build(settings: PoolSettings) -> Engine:
        return create_engine(
            DATABASE_URL,
            poolclass=QueuePool,
            pool_size=settings.pool_size,
            max_overflow=0,
            pool_timeout=settings.timeout_s,
            pool_pre_ping=True,
        )

    def reconfigure(self, settings: PoolSettings) -> None:
        with self._lock:
            old, self.engine, self.settings = self.engine, self._build(settings), settings
        old.dispose()  # Connections still checked out close when returned.
        log.info(
            "db pool configured size=%d max_overflow=0 timeout=%ss",
            settings.pool_size,
            settings.timeout_s,
        )

    def in_use(self) -> int:
        return self.engine.pool.checkedout()  # type: ignore[attr-defined]


pool = Pool()

meter.create_observable_gauge(
    "db_pool_connections_in_use",
    callbacks=[lambda _: [metrics.Observation(pool.in_use(), {"pool": "orders-db"})]],
    description="Connections currently checked out of the orders-db pool.",
)
meter.create_observable_gauge(
    "db_pool_size",
    callbacks=[lambda _: [metrics.Observation(pool.settings.pool_size, {"pool": "orders-db"})]],
    description="Maximum connections in the orders-db pool.",
)
checkouts = meter.create_counter("checkouts_total", description="Checkout attempts by outcome.")

app = FastAPI(title="checkout-api", version=APP_VERSION)


@app.on_event("startup")
def create_schema() -> None:
    with pool.engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS orders ("
                " id uuid PRIMARY KEY, amount_cents integer NOT NULL,"
                " created_at timestamptz NOT NULL DEFAULT now())"
            )
        )
    log.info(
        "checkout-api %s started, db pool size=%d max_overflow=0 timeout=%ss",
        APP_VERSION,
        pool.settings.pool_size,
        pool.settings.timeout_s,
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": APP_VERSION}


@app.post("/checkout")
def checkout() -> dict[str, str]:
    """Sync handler: FastAPI runs it in a worker thread, so a blocked pool wait is real."""
    order_id = uuid.uuid4()
    try:
        with tracer.start_as_current_span("db.pool.acquire") as span:
            span.set_attribute("db.pool.size", pool.settings.pool_size)
            span.set_attribute("db.pool.timeout_s", pool.settings.timeout_s)
            conn = pool.engine.connect()
    except PoolTimeoutError:
        checkouts.add(1, {"outcome": "pool_timeout"})
        log.error(
            "checkout %s failed: timed out waiting %ss for a connection from orders-db pool "
            "(size=%d, in_use=%d)",
            order_id,
            pool.settings.timeout_s,
            pool.settings.pool_size,
            pool.in_use(),
        )
        raise HTTPException(status_code=503, detail="database busy, try again") from None

    with conn:
        conn.execute(text("SELECT pg_sleep(:s)"), {"s": random.uniform(0.15, 0.25)})
        conn.execute(
            text("INSERT INTO orders (id, amount_cents) VALUES (:id, :amount)"),
            {"id": order_id, "amount": random.randint(500, 20000)},
        )
        conn.commit()

    checkouts.add(1, {"outcome": "ok"})
    log.info("checkout %s completed", order_id)
    return {"order_id": str(order_id)}


@app.get("/admin/fault")
def get_fault() -> PoolSettings:
    return pool.settings


@app.post("/admin/fault")
def start_fault(settings: PoolSettings | None = None) -> PoolSettings:
    """Shrink the pool. Defaults to the incident's settings: 5 connections, 2s timeout."""
    pool.reconfigure(settings or PoolSettings(pool_size=5, timeout_s=2))
    return pool.settings


@app.delete("/admin/fault")
def stop_fault() -> PoolSettings:
    pool.reconfigure(PoolSettings(pool_size=NORMAL_POOL_SIZE, timeout_s=NORMAL_TIMEOUT_S))
    return pool.settings
