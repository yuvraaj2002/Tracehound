"""Integration storage against PostgreSQL. Credentials are AES-GCM encrypted before insert."""

import base64
import binascii
import os
import secrets
from collections.abc import Sequence
from typing import Any
from uuid import UUID, uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from psycopg import errors
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from tracehound.db import SessionFactory
from tracehound.helpers.integration_client import Connection
from tracehound.models import Integration
from tracehound.schemas import (
    IntegrationCreateRequest,
    IntegrationList,
    IntegrationSummary,
    IntegrationUpdateRequest,
)
from tracehound.schemas.integration import (
    BasicAuth,
    BearerAuth,
    IntegrationAuth,
    IntegrationKind,
)


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


# The telemetry signals an investigation needs, each served by one integration kind.
REQUIRED_SIGNALS: dict[str, IntegrationKind] = {
    "logs": "loki",
    "metrics": "prometheus",
    "dependency traces": "tempo",
    "deploys": "github",
}


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

    def __init__(self, sessions: SessionFactory, encryption_key: bytes) -> None:
        self._sessions = sessions
        self._box = SecretBox(encryption_key)

    @staticmethod
    def auth_parts(auth: IntegrationAuth) -> tuple[dict[str, Any], str | None]:
        """Return the auth fields to store in the clear and the secret to encrypt, if any."""
        match auth:
            case BasicAuth(username=username, password=password):
                return {"auth_type": "basic", "username": username}, password.get_secret_value()
            case BearerAuth(token=token):
                return {"auth_type": "bearer"}, token.get_secret_value()
        return {"auth_type": auth.type}, None

    @classmethod
    def split_auth(cls, request: IntegrationCreateRequest) -> tuple[dict[str, Any], str | None]:
        """Return the config to store in the clear and the secret to encrypt, if any."""
        fields, secret = cls.auth_parts(request.auth)
        return {**request.config.model_dump(), **fields}, secret

    @classmethod
    def merge_update(
        cls, config: dict[str, Any], request: IntegrationUpdateRequest
    ) -> tuple[dict[str, Any], bool, str | None]:
        """Apply `request` to a stored config.

        Returns the new config, whether the stored secret is replaced, and the new secret.
        """
        merged = dict(config)
        if request.config is not None:
            merged.update(request.config.model_dump(exclude_unset=True))
        if request.auth is None:
            return merged, False, None
        merged.pop("username", None)
        fields, secret = cls.auth_parts(request.auth)
        return {**merged, **fields}, True, secret

    @staticmethod
    def _summary(row: Integration) -> IntegrationSummary:
        return IntegrationSummary(
            id=row.id,
            kind=row.kind,  # type: ignore[arg-type]
            config=row.config,
            has_secret=row.secret_ciphertext is not None,
            status=row.status,  # type: ignore[arg-type]
            last_tested_at=row.last_tested_at,
            last_error=row.last_error,
            created_at=row.created_at,
        )

    def _seal(self, integration_id: UUID, secret: str | None) -> tuple[bytes | None, int | None]:
        """The ciphertext and key version to store for `secret`, or (None, None) without one."""
        if secret is None:
            return None, None
        return self._box.encrypt(secret, integration_id.bytes), self.KEY_VERSION

    def create(self, user_id: UUID, request: IntegrationCreateRequest) -> IntegrationSummary:
        """Store a new integration for `user_id`. Raises `IntegrationExists` on a duplicate kind."""
        integration_id = uuid4()
        config, secret = self.split_auth(request)
        ciphertext, key_version = self._seal(integration_id, secret)
        row = Integration(
            id=integration_id,
            user_id=user_id,
            kind=request.kind,
            config=config,
            secret_ciphertext=ciphertext,
            secret_key_version=key_version,
        )
        try:
            with self._sessions.begin() as session:
                session.add(row)
                session.flush()
                session.refresh(row)  # load status and created_at filled by the database
                return self._summary(row)
        except IntegrityError as exc:
            if isinstance(exc.orig, errors.UniqueViolation):
                raise IntegrationExists(request.kind) from exc
            raise

    def list(self, user_id: UUID) -> IntegrationList:
        """Return all of the user's integrations, oldest first.

        There is at most one per kind, so the list stays small and is not paginated.
        """
        stmt = (
            select(Integration)
            .where(Integration.user_id == user_id)
            .order_by(Integration.created_at, Integration.id)
        )
        with self._sessions() as session:
            rows = session.scalars(stmt).all()
        return IntegrationList(items=[self._summary(row) for row in rows])

    def missing_signals(self, user_id: UUID) -> Sequence[str]:
        """Return the names of the required signals `user_id` has no integration for."""
        with self._sessions() as session:
            connected = set(
                session.scalars(select(Integration.kind).where(Integration.user_id == user_id))
            )
        return [name for name, kind in REQUIRED_SIGNALS.items() if kind not in connected]

    def update(
        self, user_id: UUID, integration_id: UUID, request: IntegrationUpdateRequest
    ) -> IntegrationSummary | None:
        """Change an integration's settings and, if `auth` is sent, its credential.

        The previous test result no longer applies, so the status goes back to untested.
        Returns None when the integration isn't the user's.
        """
        stmt = (
            select(Integration)
            .where(Integration.id == integration_id, Integration.user_id == user_id)
            .with_for_update()
        )
        with self._sessions.begin() as session:
            row = session.scalars(stmt).first()
            if row is None:
                return None
            config, replace_secret, secret = self.merge_update(row.config, request)
            row.config = config
            if replace_secret:
                row.secret_ciphertext, row.secret_key_version = self._seal(integration_id, secret)
            row.status = "untested"
            row.last_tested_at = None
            row.last_error = None
            row.updated_at = func.now()  # type: ignore[assignment]
            session.flush()
            session.refresh(row)
            return self._summary(row)

    def _to_connection(self, row: Integration) -> Connection:
        """Decrypt a row's credential. Raises if it was sealed with a key this build lacks."""
        secret = None
        if row.secret_ciphertext is not None:
            if row.secret_key_version != self.KEY_VERSION:
                raise RuntimeError(
                    f"integration {row.id} uses key version {row.secret_key_version},"
                    f" only {self.KEY_VERSION} is loaded"
                )
            secret = self._box.decrypt(bytes(row.secret_ciphertext), row.id.bytes)
        return Connection(id=row.id, kind=row.kind, config=row.config, secret=secret)  # type: ignore[arg-type]

    def connection(self, user_id: UUID, integration_id: UUID) -> Connection | None:
        """One of the user's integrations with its decrypted credential, or None if not theirs."""
        stmt = select(Integration).where(
            Integration.id == integration_id, Integration.user_id == user_id
        )
        with self._sessions() as session:
            row = session.scalars(stmt).first()
        return None if row is None else self._to_connection(row)

    def connections(self, user_id: UUID) -> dict[IntegrationKind, Connection]:
        """All of the user's integrations with decrypted credentials, keyed by kind."""
        with self._sessions() as session:
            rows = session.scalars(select(Integration).where(Integration.user_id == user_id)).all()
        return {row.kind: self._to_connection(row) for row in rows}  # type: ignore[misc]

    def record_test(
        self, user_id: UUID, integration_id: UUID, error: str | None
    ) -> IntegrationSummary | None:
        """Store a connection test's outcome: active on success, else failing with `error`."""
        stmt = select(Integration).where(
            Integration.id == integration_id, Integration.user_id == user_id
        )
        with self._sessions.begin() as session:
            row = session.scalars(stmt).first()
            if row is None:
                return None
            row.status = "active" if error is None else "failing"
            row.last_tested_at = func.now()  # type: ignore[assignment]
            row.last_error = error
            session.flush()
            session.refresh(row)
            return self._summary(row)

    def delete(self, user_id: UUID, integration_id: UUID) -> bool:
        """Permanently delete `integration_id` and its encrypted credential.

        A hard delete, so the user can connect the same kind again. Returns False when the
        integration isn't the user's.
        """
        stmt = (
            delete(Integration)
            .where(Integration.id == integration_id, Integration.user_id == user_id)
            .returning(Integration.id)
        )
        with self._sessions.begin() as session:
            return session.execute(stmt).first() is not None
