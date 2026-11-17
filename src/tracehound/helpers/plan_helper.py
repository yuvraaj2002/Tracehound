"""Plan catalogue reads against PostgreSQL."""

from sqlalchemy import and_, select
from sqlalchemy.orm import contains_eager

from tracehound.db import SessionFactory
from tracehound.models import Plan, PlanPrice
from tracehound.schemas import PlanList, PlanSummary
from tracehound.schemas import PlanPrice as PlanPriceSchema


class PlanCatalog:
    """Reads the plans on offer and their live prices."""

    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    def list(self) -> PlanList:
        """Return active plans in `sort_order`, each with its active prices.

        A plan with no active price (e.g. a free plan) is listed with an empty `prices`.
        """
        # One query: LEFT JOIN only the active prices and load them into `Plan.prices`.
        stmt = (
            select(Plan)
            .outerjoin(PlanPrice, and_(PlanPrice.plan_id == Plan.id, PlanPrice.is_active))
            .options(contains_eager(Plan.prices))
            .where(Plan.is_active)
            .order_by(
                Plan.sort_order,
                Plan.code,
                PlanPrice.billing_interval == "year",
                PlanPrice.currency,
            )
        )
        with self._sessions() as session:
            plans = session.scalars(stmt).unique().all()
            return PlanList(
                items=[
                    PlanSummary(
                        code=plan.code,
                        display_name=plan.display_name,
                        credits=plan.credits,
                        prices=[
                            PlanPriceSchema(
                                currency=price.currency,
                                amount_minor=price.price_minor,
                                billing_interval=price.billing_interval,  # type: ignore[arg-type]
                            )
                            for price in plan.prices
                        ],
                    )
                    for plan in plans
                ]
            )
