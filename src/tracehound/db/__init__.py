"""Local SQLite database setup. Table-specific queries live in `tracehound.helpers`."""

from tracehound.db.setup import connect, init_db

__all__ = ["connect", "init_db"]
