"""Declarative base shared by every ORM model.

The schema is owned by the SQL files in `supabase/migrations`; these classes mirror it so the
code can query tables as Python objects. A schema change needs a migration *and* a matching
edit here. `tests/integration/test_models_match_migrations.py` fails when the two drift.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, MetaData, Table, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    metadata = MetaData()


# Supabase's own user table. Only `id` is declared, so foreign keys to it resolve; the app never
# writes here.
auth_users = Table("users", Base.metadata, Column("id", Uuid, primary_key=True), schema="auth")


class Timestamps:
    """`created_at` / `updated_at` columns. The database fills both on insert."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
