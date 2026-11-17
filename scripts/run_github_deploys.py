"""Print what goes into ``GitHubDeploySource.fetch`` and what comes back out.

Default mode uses a fixed mock GitHub response (no network, no token) so you can see the
mapping clearly. Pass ``--live owner/repo`` to hit the real API instead.

Usage:
    uv run python scripts/run_github_deploys.py
    uv run python scripts/run_github_deploys.py --live yuvraaj2002/checkout-api-sim
    uv run python scripts/run_github_deploys.py --live yuvraaj2002/checkout-api-sim --hours 48

Live mode auth: ``GITHUB_TOKEN``, or ``gh auth token``.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from tracehound.tools.deploys import GitHubDeploySource

# Same shape GitHub returns (newest first). Used only in mock mode.
_MOCK_DEPLOYMENTS = [
    {
        "id": 3,
        "sha": "0000003",
        "ref": "main",
        "payload": {
            "version": "1.14.0",
            "config_diff": {"DB_POOL_SIZE": {"old": "20", "new": "5"}},
        },
        "description": "deploy 1.14.0",
        "creator": {"login": "deploy-bot"},
        "created_at": "2026-10-15T13:52:00Z",
    },
    {
        "id": 2,
        "sha": "0000002",
        "ref": "v1.13.4",
        "payload": {},
        "description": "deploy v1.13.4",
        "creator": {"login": "deploy-bot"},
        "created_at": "2026-10-15T12:00:00Z",
    },
    {
        "id": 1,
        "sha": "0000001",
        "ref": "v1.13.3",
        "payload": {},
        "description": "deploy v1.13.3",
        "creator": {"login": "deploy-bot"},
        "created_at": "2026-10-14T12:00:00Z",
    },
]


def _token() -> str:
    if token := os.environ.get("GITHUB_TOKEN"):
        return token
    return subprocess.run(
        ["gh", "auth", "token"], capture_output=True, text=True, check=True
    ).stdout.strip()


def _mock_source(repo: str) -> GitHubDeploySource:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_MOCK_DEPLOYMENTS)

    client = httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(handler))
    return GitHubDeploySource(client, repos={"checkout-api": repo})


def _live_source(repo: str, environment: str) -> GitHubDeploySource:
    client = httpx.Client(
        base_url="https://api.github.com",
        headers={
            "Authorization": f"Bearer {_token()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=30,
    )
    return GitHubDeploySource(client, repos={"checkout-api": repo}, environment=environment)


def _print_section(title: str, payload: Any) -> None:
    print(f"\n===== {title} =====")
    if isinstance(payload, (dict, list)):
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(payload)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--live",
        metavar="OWNER/REPO",
        help="Call the real GitHub API for this repo instead of the mock response",
    )
    parser.add_argument(
        "--hours",
        type=float,
        default=24.0,
        help="Live mode only: look back this many hours from now (default: 24)",
    )
    parser.add_argument("--environment", default="production")
    args = parser.parse_args()

    if args.live:
        repo = args.live
        environment = args.environment
        end = datetime.now(UTC)
        start = end - timedelta(hours=args.hours)
        source = _live_source(repo, environment)
        raw_preview = (
            "Live mode: raw GitHub JSON is whatever "
            f"GET /repos/{repo}/deployments?environment={environment} returns."
        )
    else:
        repo = "acme/checkout"
        environment = "production"
        start = datetime(2026, 10, 15, 13, 0, tzinfo=UTC)
        end = datetime(2026, 10, 15, 14, 30, tzinfo=UTC)
        source = _mock_source(repo)
        raw_preview = _MOCK_DEPLOYMENTS

    services = {"checkout-api"}
    fetch_input = {
        "services": sorted(services),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "repos": {"checkout-api": repo},
        "environment": environment,
    }

    _print_section("INPUT (fetch arguments)", fetch_input)
    _print_section("INPUT (raw GitHub deployments, newest first)", raw_preview)

    deploys = source.fetch(services, start, end)

    _print_section(
        "OUTPUT (Deploy records)",
        [d.model_dump(mode="json") for d in deploys],
    )
    print(f"\n{len(deploys)} deploy(s) in window.")


if __name__ == "__main__":
    main()
