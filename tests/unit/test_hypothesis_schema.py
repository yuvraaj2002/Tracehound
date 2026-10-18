import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from tracehound.schemas import ConfidenceBand, Hypothesis, HypothesisStatus

GROUND_TRUTH = Path(__file__).resolve().parents[2] / "ground_truth"


def _hypothesis(**override: Any) -> dict[str, Any]:
    return {
        "run_id": str(uuid4()),
        "statement": "checkout-api 1.14.0 shrank the DB connection pool",
        "mechanism": "Pool of 5 is below the ~8 concurrent connections traffic needs",
        "confidence": "high",
        "confidence_rationale": "Onset matches the deploy and spans show pool acquire timeouts",
        "supporting_evidence_ids": ["dep-002", "log-006"],
        "verification_steps": [
            {
                "check": "Compare db.pool.acquire span durations before and after dep-002",
                "expected_if_true": "Acquire time jumps to ~2s right after 13:52",
            }
        ],
        **override,
    }


def test_accepts_valid_hypothesis() -> None:
    hypothesis = Hypothesis.model_validate(_hypothesis())
    assert hypothesis.status is HypothesisStatus.PROPOSED
    assert hypothesis.confidence is ConfidenceBand.HIGH
    assert hypothesis.id
    assert hypothesis.cited_evidence_ids == {"dep-002", "log-006"}


@pytest.mark.parametrize(
    "override",
    [
        {"supporting_evidence_ids": []},  # uncited claim
        {"supporting_evidence_ids": ["dep-002", "dep-002"]},
        {"supporting_evidence_ids": ["bad id"]},
        {"contradicting_evidence_ids": ["dep-002"]},  # both supports and contradicts
        {"status": "refuted"},  # refuted without counterevidence
        {"status": "supported", "supporting_evidence_ids": []},
        {"confidence": 0.9},
        {"confidence_rationale": ""},
        {"verification_steps": [{"check": "look at logs"}]},
        {"unexpected": "field"},
    ],
)
def test_rejects_invalid_hypothesis(override: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Hypothesis.model_validate(_hypothesis(**override))


def test_refuted_hypothesis_needs_only_counterevidence() -> None:
    hypothesis = Hypothesis.model_validate(
        _hypothesis(
            status="refuted",
            supporting_evidence_ids=[],
            contradicting_evidence_ids=["met-001"],
        )
    )
    assert hypothesis.cited_evidence_ids == {"met-001"}


@pytest.mark.parametrize("path", sorted(GROUND_TRUTH.glob("*.json")), ids=lambda p: p.stem)
def test_ground_truth_fits_hypothesis_schema(path: Path) -> None:
    truth = json.loads(path.read_text())
    run_id = uuid4()
    Hypothesis(
        run_id=run_id,
        statement=truth["root_cause"]["statement"],
        mechanism=truth["root_cause"]["mechanism"],
        confidence=ConfidenceBand.HIGH,
        confidence_rationale="ground truth",
        status=HypothesisStatus.SUPPORTED,
        supporting_evidence_ids=truth["key_evidence_ids"],
    )
    for ruled_out in truth["ruled_out"]:
        Hypothesis(
            run_id=run_id,
            statement=ruled_out["hypothesis"],
            mechanism=ruled_out["reason"],
            confidence=ConfidenceBand.HIGH,
            confidence_rationale="ground truth",
            status=HypothesisStatus.REFUTED,
            contradicting_evidence_ids=ruled_out["evidence_ids"],
        )
