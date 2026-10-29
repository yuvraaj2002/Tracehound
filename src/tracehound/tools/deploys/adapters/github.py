"""Deploy source for GitHub Deployments: the REST deployments list, mapped to ``Deploy``."""

import json
from datetime import datetime
from typing import Any

import httpx

from tracehound.schemas.telemetry import Deploy
from tracehound.tools.deploys.base import DeploySource

_PER_PAGE = 100


class GitHubDeploySource(DeploySource):
    """Reads deployments from ``/repos/{owner}/{repo}/deployments``, one repo per service.

    ``repos`` maps each service to its ``owner/repo``. Services sharing a repo (a monorepo) are
    told apart by a ``service`` key in the deployment payload; a deployment without one belongs to
    every service mapped to that repo. ``version`` and ``config_diff`` also come from the payload
    when the pipeline sets them, otherwise the version is the deployed ref. ``deployed_at`` is when
    the deployment was created, and ``previous_version`` is the version of the deployment before
    it, so the list is read back one deployment past ``start``.
    """

    def __init__(
        self,
        client: httpx.Client,
        repos: dict[str, str],
        environment: str = "production",
        max_pages: int = 10,
    ) -> None:
        self._client = client  # base_url (api.github.com or GHES) and token set by caller
        self._repos = repos
        self._environment = environment
        self._max_pages = max_pages

    def fetch(self, services: set[str], start: datetime, end: datetime) -> list[Deploy]:
        """Deploys to ``services`` with ``start <= deployed_at <= end``, oldest first.

        Services missing from ``repos`` have no deploys. Raises ``ValueError`` if a repo needs
        more than ``max_pages`` pages to reach ``start``.
        """
        deploys = [
            deploy
            for service in sorted(services & self._repos.keys())
            for deploy in self._service_deploys(service, start, end)
        ]
        return sorted(deploys, key=lambda d: (d.deployed_at, d.id))

    def _service_deploys(self, service: str, start: datetime, end: datetime) -> list[Deploy]:
        newest_first = [
            raw for raw in self._list(self._repos[service], start) if _service_of(raw, service)
        ]
        deploys = []
        for raw, older in zip(newest_first, [*newest_first[1:], None], strict=True):
            deploy = _to_deploy(raw, service, _version(older) if older else None)
            if start <= deploy.deployed_at <= end:
                deploys.append(deploy)
        return deploys

    def _list(self, repo: str, start: datetime) -> list[dict[str, Any]]:
        """Deployments newest first, through the first one created before ``start``."""
        result: list[dict[str, Any]] = []
        for page in range(1, self._max_pages + 1):
            response = self._client.get(
                f"/repos/{repo}/deployments",
                params={"environment": self._environment, "per_page": _PER_PAGE, "page": page},
            )
            response.raise_for_status()
            batch = response.json()
            if not isinstance(batch, list):
                raise ValueError(f"unexpected GitHub response: {str(batch)[:200]}")
            result.extend(batch)
            # One deployment before start is enough for the earliest in-window previous_version.
            if len(batch) < _PER_PAGE or any(_created(raw) < start for raw in batch):
                return result
        raise ValueError(f"{repo} has more than {self._max_pages} pages of deployments after start")


def _to_deploy(raw: dict[str, Any], service: str, previous_version: str | None) -> Deploy:
    payload = _payload(raw)
    return Deploy(
        id=f"gh-{raw['id']}",
        service=service,
        version=_version(raw),
        previous_version=previous_version,
        deployed_at=_created(raw),
        author=(raw.get("creator") or {}).get("login", "unknown"),
        commit=raw["sha"],
        change_summary=raw.get("description") or "",
        config_diff=payload.get("config_diff") or {},
    )


def _version(raw: dict[str, Any]) -> str:
    return str(_payload(raw).get("version") or raw["ref"])


def _service_of(raw: dict[str, Any], service: str) -> bool:
    named = _payload(raw).get("service")
    return named is None or named == service


def _created(raw: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(raw["created_at"])


def _payload(raw: dict[str, Any]) -> dict[str, Any]:
    """GitHub returns the payload as an object, or as the string it was created with."""
    payload = raw.get("payload")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            return {}
    return payload if isinstance(payload, dict) else {}
