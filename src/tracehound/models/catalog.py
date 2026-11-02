"""`service_catalogs`: each user's uploaded Backstage catalog and its parsed form."""

from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from tracehound.models.base import Base, Timestamps


class ServiceCatalogRow(Timestamps, Base):
    """Named `...Row` so it doesn't clash with the `ServiceCatalog` API schema."""

    __tablename__ = "service_catalogs"
    __table_args__ = (
        CheckConstraint("octet_length(source) <= 1048576"),
        CheckConstraint("jsonb_typeof(catalog) = 'object'"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("auth.users.id", ondelete="CASCADE"), primary_key=True
    )
    source: Mapped[str] = mapped_column(Text)
    catalog: Mapped[dict[str, Any]] = mapped_column(JSONB)
