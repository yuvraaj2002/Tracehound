"""Plan contracts: what each subscription plan gives and what it costs."""

from typing import Literal

from pydantic import BaseModel

BillingInterval = Literal["month", "year"]


class PlanPrice(BaseModel):
    """A live price. `amount_minor` is in the currency's minor unit, so $19.99 is 1999."""

    currency: str
    amount_minor: int
    billing_interval: BillingInterval


class PlanSummary(BaseModel):
    """An active plan with its live prices, monthly before yearly."""

    code: str
    display_name: str
    credits: int
    prices: list[PlanPrice]


class PlanList(BaseModel):
    """Response for ``GET /v1/plans``, in pricing-page order."""

    items: list[PlanSummary]
