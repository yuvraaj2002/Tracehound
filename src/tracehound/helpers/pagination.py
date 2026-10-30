"""Opaque keyset cursors over `(created_at, id)`, shared by the paginated list endpoints."""

import base64
import binascii
import json
from datetime import datetime
from uuid import UUID


class InvalidCursor(ValueError):
    """The pagination cursor was not produced by one of our list endpoints."""


def encode_cursor(created_at: datetime, row_id: UUID) -> str:
    raw = json.dumps({"created_at": created_at.isoformat(), "id": str(row_id)})
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return datetime.fromisoformat(data["created_at"]), UUID(data["id"])
    except (binascii.Error, ValueError, KeyError, TypeError) as exc:
        raise InvalidCursor(cursor) from exc
