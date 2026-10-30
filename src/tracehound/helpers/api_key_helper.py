"""API key issuing against PostgreSQL. Only an HMAC of each key is stored."""

import hashlib
import hmac
import os
import secrets
from uuid import UUID

from psycopg_pool import ConnectionPool

from tracehound.helpers.pagination import decode_cursor, encode_cursor
from tracehound.schemas import ApiKeyCreated, ApiKeyPage, ApiKeySummary


def api_key_hash_secret() -> str:
    """Return `API_KEY_HASH_SECRET`, failing early with a clear message when it is unset."""
    secret = os.environ.get("API_KEY_HASH_SECRET")
    if not secret:
        raise RuntimeError("API_KEY_HASH_SECRET is not set. Add it to .env (see README).")
    return secret


class ApiKeyManagement:
    """Creates API keys for users. Keys look like `th_<43 url-safe chars>` (256 random bits)."""

    KEY_PREFIX = "th_"
    PREFIX_LENGTH = len(KEY_PREFIX) + 4
    SUFFIX_LENGTH = 4
    PAGE_SIZE = 10

    def __init__(self, pool: ConnectionPool, hash_secret: str) -> None:
        self._pool = pool
        self._hash_secret = hash_secret.encode()

    @classmethod
    def generate_raw_key(cls) -> str:
        return cls.KEY_PREFIX + secrets.token_urlsafe(32)

    @classmethod
    def display_parts(cls, raw_key: str) -> tuple[str, str]:
        """Return the prefix and suffix the UI shows to identify a key, e.g. `th_AbCd…WxYz`."""
        return raw_key[: cls.PREFIX_LENGTH], raw_key[-cls.SUFFIX_LENGTH :]

    def hash_key(self, raw_key: str) -> str:
        """HMAC-SHA256 of the key, so a leaked table can't be checked against guesses."""
        return hmac.new(self._hash_secret, raw_key.encode(), hashlib.sha256).hexdigest()

    def create(self, user_id: UUID, name: str) -> ApiKeyCreated:
        """Store a new key for `user_id` and return it, including the raw key."""
        raw_key = self.generate_raw_key()
        prefix, suffix = self.display_parts(raw_key)
        with self._pool.connection() as conn:
            row = conn.execute(
                "INSERT INTO api_keys (user_id, name, hash, prefix, suffix)"
                " VALUES (%s, %s, %s, %s, %s) RETURNING id, created_at",
                (user_id, name, self.hash_key(raw_key), prefix, suffix),
            ).fetchone()
        assert row is not None
        return ApiKeyCreated(
            id=row["id"],
            name=name,
            key=raw_key,
            prefix=prefix,
            suffix=suffix,
            created_at=row["created_at"],
        )

    def revoke(self, user_id: UUID, key_id: UUID) -> bool:
        """Soft-delete `key_id` by setting `revoked_at`.

        Returns False when the key isn't the user's or is already revoked.
        """
        with self._pool.connection() as conn:
            row = conn.execute(
                "UPDATE api_keys SET revoked_at = now(), updated_at = now()"
                " WHERE id = %s AND user_id = %s AND revoked_at IS NULL RETURNING id",
                (key_id, user_id),
            ).fetchone()
        return row is not None

    def list(self, user_id: UUID, cursor: str | None = None) -> ApiKeyPage:
        """Return one page of the user's active keys, newest first.

        Raises `InvalidCursor` when `cursor` is malformed.
        """
        after = decode_cursor(cursor) if cursor else None
        query = (
            "SELECT id, name, prefix, suffix, created_at, last_used_at FROM api_keys"
            " WHERE user_id = %s AND revoked_at IS NULL"
        )
        params: list[object] = [user_id]
        if after is not None:
            query += " AND (created_at, id) < (%s, %s)"
            params.extend(after)
        query += " ORDER BY created_at DESC, id DESC LIMIT %s"
        params.append(self.PAGE_SIZE + 1)
        with self._pool.connection() as conn:
            rows = conn.execute(query, params).fetchall()
        items = [ApiKeySummary(**row) for row in rows[: self.PAGE_SIZE]]
        next_cursor = None
        if len(rows) > self.PAGE_SIZE:
            last = items[-1]
            next_cursor = encode_cursor(last.created_at, last.id)
        return ApiKeyPage(items=items, next_cursor=next_cursor)
