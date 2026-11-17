"""The ORM models in `tracehound.models` must match the tables `supabase/migrations` build.

The migrations own the schema; the models mirror it. This fails when one changes without the
other. Run with: uv run pytest -m integration
"""

from sqlalchemy import Engine, inspect

from tests.integration.test_api_key_db import engine, pytestmark, schema
from tracehound.models import Base

__all__ = ["engine", "pytestmark", "schema"]


def test_every_model_column_matches_the_migrated_table(engine: Engine, schema: str) -> None:
    inspector = inspect(engine)
    for table in Base.metadata.sorted_tables:
        if table.schema == "auth":
            continue  # Supabase's table, not ours
        migrated = {c["name"]: c for c in inspector.get_columns(table.name, schema=schema)}
        assert set(migrated) == set(table.columns.keys()), table.name
        for column in table.columns:
            assert migrated[column.name]["nullable"] == column.nullable, (
                f"{table.name}.{column.name}"
            )
        pk = inspector.get_pk_constraint(table.name, schema=schema)["constrained_columns"]
        assert set(pk) == {c.name for c in table.primary_key}, table.name


def test_no_migrated_table_is_missing_a_model(engine: Engine, schema: str) -> None:
    modelled = {t.name for t in Base.metadata.sorted_tables if t.schema is None}
    assert set(inspect(engine).get_table_names(schema=schema)) == modelled
