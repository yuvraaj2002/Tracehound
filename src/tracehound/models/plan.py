"""`plans` (what a plan gives) and `plan_prices` (what it costs, versioned per row)."""

from uuid import UUID

from sqlalchemy import CHAR, CheckConstraint, ForeignKey, Index, SmallInteger, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tracehound.models.base import Base, Timestamps


class Plan(Timestamps, Base):
    __tablename__ = "plans"
    __table_args__ = (
        CheckConstraint("code ~ '^[a-z0-9_]{1,50}$'"),
        CheckConstraint("length(display_name) between 1 and 100"),
        CheckConstraint("credits >= 0"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    code: Mapped[str] = mapped_column(Text, unique=True)
    display_name: Mapped[str] = mapped_column(Text)
    credits: Mapped[int]
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))

    prices: Mapped[list["PlanPrice"]] = relationship(back_populates="plan")


class PlanPrice(Timestamps, Base):
    __tablename__ = "plan_prices"
    __table_args__ = (
        CheckConstraint("currency ~ '^[A-Z]{3}$'"),
        CheckConstraint("price_minor >= 0"),
        CheckConstraint("billing_interval in ('month', 'year')"),
        Index("plan_prices_plan_id_idx", "plan_id"),
        # At most one live price per plan, currency and interval.
        Index(
            "plan_prices_active_key",
            "plan_id",
            "currency",
            "billing_interval",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    plan_id: Mapped[UUID] = mapped_column(ForeignKey("plans.id", ondelete="RESTRICT"))
    currency: Mapped[str] = mapped_column(CHAR(3))
    price_minor: Mapped[int]
    billing_interval: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))

    plan: Mapped[Plan] = relationship(back_populates="prices")
