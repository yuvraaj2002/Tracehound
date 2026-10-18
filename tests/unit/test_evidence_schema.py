from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from tracehound.schemas import Evidence, EvidenceSource, hash_payload

RECORD = {
    "id": "log-006",
    "service": "checkout-api",
    "level": "ERROR",
    "message": "Timed out acquiring DB connection after 2s",
}


def _evidence(**override: Any) -> dict[str, Any]:
    return {
        "id": "log-006",
        "run_id": str(uuid4()),
        "source_type": "log",
        "source_locator": "scenario://checkout_db_pool_exhaustion/logs.json#log-006",
        "service": "checkout-api",
        "event_time": "2026-10-15T13:56:10+05:30",
        "collected_at": "2026-10-18T10:00:00Z",
        "payload_hash": hash_payload(RECORD),
        "excerpt": "ERROR Timed out acquiring DB connection after 2s",
        **override,
    }


def test_accepts_valid_evidence() -> None:
    evidence = Evidence.model_validate(_evidence())
    assert evidence.source_type is EvidenceSource.LOG
    assert evidence.event_time.utcoffset().total_seconds() == 0
    assert evidence.event_time.isoformat() == "2026-10-15T08:26:10+00:00"
    assert evidence.metadata == {}


def test_evidence_is_immutable() -> None:
    evidence = Evidence.model_validate(_evidence())
    with pytest.raises(ValidationError):
        evidence.excerpt = "edited"  # type: ignore[misc]


@pytest.mark.parametrize(
    "override",
    [
        {"id": "log 006"},
        {"id": ""},
        {"source_type": "email"},
        {"event_time": "2026-10-15T13:56:10"},  # naive timestamp
        {"payload_hash": "abc"},
        {"excerpt": ""},
        {"service": "bad id!"},
        {"unexpected": "field"},
    ],
)
def test_rejects_invalid_evidence(override: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        Evidence.model_validate(_evidence(**override))


def test_hash_ignores_key_order() -> None:
    reordered = dict(reversed(RECORD.items()))
    assert hash_payload(reordered) == hash_payload(RECORD)
    assert hash_payload({**RECORD, "level": "WARN"}) != hash_payload(RECORD)
