"""Plan listing against real PostgreSQL. Run with: uv run pytest -m integration

Rows are written to a throwaway schema built from `supabase/migrations` (see `test_api_key_db`).
"""

from fastapi.testclient import TestClient
from psycopg_pool import ConnectionPool

from tests.integration.test_api_key_db import pool, pytestmark, schema
from tracehound.api.app import create_app

__all__ = ["pool", "pytestmark", "schema"]


def _seed(pool: ConnectionPool) -> None:
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO plans (code, display_name, credits, sort_order, is_active) VALUES"
            " ('pro', 'Pro', 200, 1, true), ('free', 'Free', 10, 0, true),"
            " ('legacy', 'Legacy', 50, 2, false)"
        )
        conn.execute(
            "INSERT INTO plan_prices (plan_id, currency, price_minor, billing_interval, is_active)"
            " SELECT id, v.currency, v.price_minor, v.billing_interval, v.is_active"
            " FROM plans JOIN (VALUES"
            "   ('pro', 'USD', 19000, 'year', true),"
            "   ('pro', 'USD', 1900, 'month', true),"
            "   ('pro', 'USD', 1500, 'month', false),"
            "   ('legacy', 'USD', 900, 'month', true)"
            " ) AS v(code, currency, price_minor, billing_interval, is_active) USING (code)"
        )


def test_lists_active_plans_and_prices(pool: ConnectionPool) -> None:
    _seed(pool)
    with TestClient(create_app(pool_factory=lambda: pool)) as client:
        response = client.get("/v1/plans")
    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {"code": "free", "display_name": "Free", "credits": 10, "prices": []},
            {
                "code": "pro",
                "display_name": "Pro",
                "credits": 200,
                "prices": [
                    {"currency": "USD", "amount_minor": 1900, "billing_interval": "month"},
                    {"currency": "USD", "amount_minor": 19000, "billing_interval": "year"},
                ],
            },
        ]
    }
