"""Scenario fixtures and their ground truth stay valid and consistent."""

import json
from pathlib import Path

import pytest

from tracehound.schemas import IncidentCreateRequest

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = ROOT / "scenarios"
GROUND_TRUTH = ROOT / "ground_truth"
EVIDENCE_FILES = ("deploys.json", "logs.json", "metrics.json", "traces.json")
SCENARIO_DIRS = sorted(p for p in SCENARIOS.iterdir() if p.is_dir())


def _load(path: Path) -> object:
    return json.loads(path.read_text())


def _evidence_ids(scenario: Path) -> list[str]:
    return [item["id"] for name in EVIDENCE_FILES for item in _load(scenario / name)]


def test_at_least_one_scenario() -> None:
    assert SCENARIO_DIRS


@pytest.mark.parametrize("scenario", SCENARIO_DIRS, ids=lambda p: p.name)
def test_scenario_is_complete(scenario: Path) -> None:
    for name in ("scenario.json", "topology.json", *EVIDENCE_FILES):
        assert (scenario / name).is_file(), name
    meta = _load(scenario / "scenario.json")
    assert meta["id"] == scenario.name
    IncidentCreateRequest.model_validate(meta["alert"])


@pytest.mark.parametrize("scenario", SCENARIO_DIRS, ids=lambda p: p.name)
def test_evidence_ids_are_unique(scenario: Path) -> None:
    ids = _evidence_ids(scenario)
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("scenario", SCENARIO_DIRS, ids=lambda p: p.name)
def test_ground_truth_references_real_evidence(scenario: Path) -> None:
    truth = _load(GROUND_TRUTH / f"{scenario.name}.json")
    assert truth["scenario_id"] == scenario.name
    known = set(_evidence_ids(scenario))
    referenced = {
        *truth["key_evidence_ids"],
        *truth["supporting_evidence_ids"],
        truth["root_cause"]["deploy_id"],
        *(i for r in truth["ruled_out"] for i in r["evidence_ids"]),
    }
    assert referenced <= known, referenced - known


def test_ground_truth_is_not_inside_scenarios() -> None:
    assert not list(SCENARIOS.rglob("*ground_truth*"))
