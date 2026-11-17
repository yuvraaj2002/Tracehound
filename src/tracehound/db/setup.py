"""SQLAlchemy engine and session setup. The schema lives in `supabase/migrations`."""

import os
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

SessionFactory = sessionmaker[Session]


def database_url() -> str:
    """Return `DATABASE_URL`, failing early with a clear message when it is unset."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set. Add it to .env (see README).")
    return url


def sqlalchemy_url(url: str) -> str:
    """Point a plain ``postgresql://`` URL at the psycopg 3 driver."""
    for scheme in ("postgresql://", "postgres://"):
        if url.startswith(scheme):
            return "postgresql+psycopg://" + url.removeprefix(scheme)
    return url


def create_db_engine(url: str, **connect_args: Any) -> Engine:
    """A small pool of up to 5 connections.

    Server-side prepared statements are off so the engine also works behind Supabase's
    transaction pooler. `connect_args` go to psycopg (tests pass ``options`` for search_path).
    """
    return create_engine(
        sqlalchemy_url(url),
        pool_size=5,
        max_overflow=0,
        pool_pre_ping=True,
        connect_args={"prepare_threshold": None, **connect_args},
    )


def create_session_factory(engine: Engine) -> SessionFactory:
    """Sessions that keep loaded objects readable after commit, so helpers can return them."""
    return sessionmaker(engine, expire_on_commit=False)
