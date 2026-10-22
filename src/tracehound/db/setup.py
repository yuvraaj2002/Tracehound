"""PostgreSQL connection pool setup. The schema lives in `supabase/migrations`."""

import os

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


def database_url() -> str:
    """Return `DATABASE_URL`, failing early with a clear message when it is unset."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set. Add it to .env (see README).")
    return url


def create_pool(url: str, **connect_kwargs: object) -> ConnectionPool:
    """Open a small pool whose rows can be read by column name.

    Server-side prepared statements are off so the pool also works behind Supabase's
    transaction pooler.
    """
    return ConnectionPool(
        url,
        min_size=1,
        max_size=5,
        kwargs={"row_factory": dict_row, "prepare_threshold": None, **connect_kwargs},
        open=True,
    )
