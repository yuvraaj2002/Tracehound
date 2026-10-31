"""Plan catalogue reads against PostgreSQL."""

from uuid import UUID

from psycopg_pool import ConnectionPool

from tracehound.schemas import PlanList, PlanPrice, PlanSummary


class PlanCatalog:
    """Reads the plans on offer and their live prices."""

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def list(self) -> PlanList:
        """Return active plans in `sort_order`, each with its active prices.

        A plan with no active price (e.g. a free plan) is listed with an empty `prices`.
        """
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT p.id, p.code, p.display_name, p.credits,"
                " pp.currency, pp.price_minor, pp.billing_interval"
                " FROM plans p"
                " LEFT JOIN plan_prices pp ON pp.plan_id = p.id AND pp.is_active"
                " WHERE p.is_active"
                " ORDER BY p.sort_order, p.code, pp.billing_interval = 'year', pp.currency"
            ).fetchall()
        plans: dict[UUID, PlanSummary] = {}
        for row in rows:
            plan = plans.get(row["id"])
            if plan is None:
                plan = plans[row["id"]] = PlanSummary(
                    code=row["code"],
                    display_name=row["display_name"],
                    credits=row["credits"],
                    prices=[],
                )
            if row["currency"] is not None:
                plan.prices.append(
                    PlanPrice(
                        currency=row["currency"],
                        amount_minor=row["price_minor"],
                        billing_interval=row["billing_interval"],
                    )
                )
        return PlanList(items=list(plans.values()))
