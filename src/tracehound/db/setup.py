"""Local SQLite database setup: connections and schema creation."""

import sqlite3
from contextlib import closing
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    id           TEXT PRIMARY KEY,
    run_id       TEXT NOT NULL,
    service_id   TEXT NOT NULL,
    symptom      TEXT NOT NULL,
    severity     TEXT NOT NULL,
    window_start TEXT NOT NULL,
    window_end   TEXT NOT NULL,
    trace_id     TEXT,
    state        TEXT NOT NULL DEFAULT 'CREATED',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
"""


def connect(path: Path) -> sqlite3.Connection:
    """Open a connection whose rows can be read by column name."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path: Path) -> None:
    """Create the database file and all tables if they do not exist yet."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(path)) as conn, conn:
        conn.executescript(_SCHEMA)
