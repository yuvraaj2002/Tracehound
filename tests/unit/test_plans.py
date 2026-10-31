import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tracehound.api.app import create_app
from tracehound.api.dependencies import get_plan_catalog
from tracehound.schemas import PlanList, PlanPrice, PlanSummary

CATALOG = PlanList(
    items=[
        PlanSummary(code="free", display_name="Free", credits=10, prices=[]),
        PlanSummary(
            code="pro",
            display_name="Pro",
            credits=200,
            prices=[
                PlanPrice(currency="USD", amount_minor=1900, billing_interval="month"),
                PlanPrice(currency="USD", amount_minor=19000, billing_interval="year"),
            ],
        ),
    ]
)


class MemoryPlans:
    """In-memory stand-in for `PlanCatalog`, so these tests need no database."""

    def list(self) -> PlanList:
        return CATALOG


class BrokenPlans:
    def list(self) -> PlanList:
        raise psycopg.OperationalError("connection lost")


def _app_with(plans: object) -> FastAPI:
    app = create_app(pool_factory=lambda: pytest.fail("pool should not open"))
    app.dependency_overrides[get_plan_catalog] = lambda: plans
    return app


def test_lists_plans_without_auth() -> None:
    response = TestClient(_app_with(MemoryPlans())).get("/v1/plans")
    assert response.status_code == 200
    assert response.json() == CATALOG.model_dump()
    assert response.headers["Cache-Control"] == "public, max-age=300"


def test_database_error_is_500() -> None:
    response = TestClient(_app_with(BrokenPlans())).get("/v1/plans")
    assert response.status_code == 500
    assert response.json() == {"detail": "Could not list the plans."}
    assert "Cache-Control" not in response.headers
