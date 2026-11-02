"""API key issuing against PostgreSQL. Only an HMAC of each key is stored."""

import hashlib
import hmac
import os
import secrets
from uuid import UUID

from sqlalchemy import cast, func, select, tuple_, update
from sqlalchemy.types import Text

from tracehound.db import SessionFactory
from tracehound.helpers.pagination import decode_cursor, encode_cursor
from tracehound.models import ApiKey
from tracehound.schemas import ApiKeyCreated, ApiKeyPage, ApiKeySummary


def api_key_hash_secret() -> str:
    """Return `API_KEY_HASH_SECRET`, failing early with a clear message when it is unset."""
    secret = os.environ.get("API_KEY_HASH_SECRET")
    if not secret:
        raise RuntimeError("API_KEY_HASH_SECRET is not set. Add it to .env (see README).")
    return secret


class ApiKeyLimitReached(Exception):
    """The user already has the maximum number of active keys."""


class ApiKeyManagement:
    """Creates API keys for users. Keys look like `th_<43 url-safe chars>` (256 random bits)."""

    KEY_PREFIX = "th_"
    PREFIX_LENGTH = len(KEY_PREFIX) + 4
    SUFFIX_LENGTH = 4
    PAGE_SIZE = 10
    MAX_ACTIVE_KEYS = 5  # revoked keys don't count

    def __init__(self, sessions: SessionFactory, hash_secret: str) -> None:
        self._sessions = sessions
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
        """Store a new key for `user_id` and return it, including the raw key.

        Raises `ApiKeyLimitReached` when the user already has `MAX_ACTIVE_KEYS` active keys.
        """
        raw_key = self.generate_raw_key()
        prefix, suffix = self.display_parts(raw_key)
        key = ApiKey(
            user_id=user_id, name=name, hash=self.hash_key(raw_key), prefix=prefix, suffix=suffix
        )
        with self._sessions.begin() as session:
            # Per-user lock until commit, so two concurrent requests can't both take the last slot.
            session.execute(select(func.pg_advisory_xact_lock(func.hashtext(cast(user_id, Text)))))
            active = session.scalar(
                select(func.count())
                .select_from(ApiKey)
                .where(ApiKey.user_id == user_id, ApiKey.revoked_at.is_(None))
            )
            if (active or 0) >= self.MAX_ACTIVE_KEYS:
                raise ApiKeyLimitReached(user_id)
            session.add(key)
            session.flush()  # sends the INSERT, so the database-filled id and created_at load
            return ApiKeyCreated(
                id=key.id,
                name=name,
                key=raw_key,
                prefix=prefix,
                suffix=suffix,
                created_at=key.created_at,
                updated_at=key.updated_at,
            )

    def revoke(self, user_id: UUID, key_id: UUID) -> bool:
        """Soft-delete `key_id` by setting `revoked_at`.

        Returns False when the key isn't the user's or is already revoked.
        """
        stmt = (
            update(ApiKey)
            .where(ApiKey.id == key_id, ApiKey.user_id == user_id, ApiKey.revoked_at.is_(None))
            .values(revoked_at=func.now(), updated_at=func.now())
            .returning(ApiKey.id)
        )
        with self._sessions.begin() as session:
            return session.execute(stmt).first() is not None

    def rename(self, user_id: UUID, key_id: UUID, new_name: str) -> ApiKeySummary | None:
        """Change an active key's name. Returns None when the key isn't the user's or is revoked."""
        stmt = (
            update(ApiKey)
            .where(ApiKey.id == key_id, ApiKey.user_id == user_id, ApiKey.revoked_at.is_(None))
            .values(name=new_name, updated_at=func.now())
            .returning(ApiKey)
        )
        with self._sessions.begin() as session:
            row = session.scalars(stmt).first()
            if row is None:
                return None
            return ApiKeySummary(
                id=row.id,
                name=row.name,
                prefix=row.prefix,
                suffix=row.suffix,
                created_at=row.created_at,
                updated_at=row.updated_at,
                last_used_at=row.last_used_at,
            )

    def list(self, user_id: UUID, cursor: str | None = None) -> ApiKeyPage:
        """Return one page of the user's active keys, newest first.

        Raises `InvalidCursor` when `cursor` is malformed.
        """
        after = decode_cursor(cursor) if cursor else None
        stmt = select(ApiKey).where(ApiKey.user_id == user_id, ApiKey.revoked_at.is_(None))
        if after is not None:
            stmt = stmt.where(tuple_(ApiKey.created_at, ApiKey.id) < after)
        stmt = stmt.order_by(ApiKey.created_at.desc(), ApiKey.id.desc()).limit(self.PAGE_SIZE + 1)
        with self._sessions() as session:
            rows = session.scalars(stmt).all()
        items = [
            ApiKeySummary(
                id=row.id,
                name=row.name,
                prefix=row.prefix,
                suffix=row.suffix,
                created_at=row.created_at,
                updated_at=row.updated_at,
                last_used_at=row.last_used_at,
            )
            for row in rows[: self.PAGE_SIZE]
        ]
        next_cursor = None
        if len(rows) > self.PAGE_SIZE:
            last = items[-1]
            next_cursor = encode_cursor(last.created_at, last.id)
        return ApiKeyPage(items=items, next_cursor=next_cursor)
