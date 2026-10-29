"""Integration storage against PostgreSQL. Credentials are AES-GCM encrypted before insert."""

import base64
import binascii
import os
import secrets
from typing import Any
from uuid import UUID, uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from psycopg import errors
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from tracehound.schemas import IntegrationCreateRequest, IntegrationList, IntegrationSummary
from tracehound.schemas.integration import BasicAuth, BearerAuth


def integration_encryption_key() -> bytes:
    """Return `INTEGRATION_ENCRYPTION_KEY` as 32 bytes, failing early when unset or malformed."""
    raw = os.environ.get("INTEGRATION_ENCRYPTION_KEY")
    if not raw:
        raise RuntimeError("INTEGRATION_ENCRYPTION_KEY is not set. Add it to .env (see README).")
    try:
        key = base64.urlsafe_b64decode(raw)
    except (binascii.Error, ValueError) as exc:
        raise RuntimeError("INTEGRATION_ENCRYPTION_KEY must be url-safe base64.") from exc
    if len(key) != 32:
        raise RuntimeError("INTEGRATION_ENCRYPTION_KEY must decode to 32 bytes.")
    return key


class IntegrationExists(Exception):
    """The user already has an integration of this kind."""


class SecretBox:
    """AES-256-GCM for integration credentials. Output is the 12-byte nonce then the ciphertext.

    `associated_data` (the integration ID) is authenticated but not stored in the ciphertext, so
    a ciphertext copied onto another row fails to decrypt.
    """

    NONCE_LENGTH = 12

    def __init__(self, key: bytes) -> None:
        self._aead = AESGCM(key)

    def encrypt(self, plaintext: str, associated_data: bytes) -> bytes:
        nonce = secrets.token_bytes(self.NONCE_LENGTH)
        return nonce + self._aead.encrypt(nonce, plaintext.encode(), associated_data)

    def decrypt(self, sealed: bytes, associated_data: bytes) -> str:
        nonce, ciphertext = sealed[: self.NONCE_LENGTH], sealed[self.NONCE_LENGTH :]
        return self._aead.decrypt(nonce, ciphertext, associated_data).decode()


class IntegrationManagement:
    """Stores users' telemetry backend connections."""

    KEY_VERSION = 1  # bump with a second key when rotating INTEGRATION_ENCRYPTION_KEY

    def __init__(self, pool: ConnectionPool, encryption_key: bytes) -> None:
        self._pool = pool
        self._box = SecretBox(encryption_key)

    @staticmethod
    def split_auth(request: IntegrationCreateRequest) -> tuple[dict[str, Any], str | None]:
        """Return the config to store in the clear and the secret to encrypt, if any."""
        config: dict[str, Any] = {**request.config.model_dump(), "auth_type": request.auth.type}
        match request.auth:
            case BasicAuth(username=username, password=password):
                config["username"] = username
                return config, password.get_secret_value()
            case BearerAuth(token=token):
                return config, token.get_secret_value()
        return config, None

    def create(self, user_id: UUID, request: IntegrationCreateRequest) -> IntegrationSummary:
        """Store a new integration for `user_id`. Raises `IntegrationExists` on a duplicate kind."""
        integration_id = uuid4()
        config, secret = self.split_auth(request)
        ciphertext = None if secret is None else self._box.encrypt(secret, integration_id.bytes)
        key_version = None if secret is None else self.KEY_VERSION
        try:
            with self._pool.connection() as conn:
                row = conn.execute(
                    "INSERT INTO integrations"
                    " (id, user_id, kind, config, secret_ciphertext, secret_key_version)"
                    " VALUES (%s, %s, %s, %s, %s, %s)"
                    " RETURNING status, last_tested_at, created_at",
                    (integration_id, user_id, request.kind, Jsonb(config), ciphertext, key_version),
                ).fetchone()
        except errors.UniqueViolation as exc:
            raise IntegrationExists(request.kind) from exc
        assert row is not None
        return IntegrationSummary(
            id=integration_id,
            kind=request.kind,
            config=config,
            has_secret=secret is not None,
            **row,
        )

    def list(self, user_id: UUID) -> IntegrationList:
        """Return all of the user's integrations, oldest first.

        There is at most one per kind, so the list stays small and is not paginated.
        """
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT id, kind, config, secret_ciphertext IS NOT NULL AS has_secret, status,"
                " last_tested_at, created_at FROM integrations"
                " WHERE user_id = %s ORDER BY created_at, id",
                (user_id,),
            ).fetchall()
        return IntegrationList(items=[IntegrationSummary(**row) for row in rows])
