"""Fetches GitHub Deployments for a time window and returns them as Tracehound ``Deploy``s."""

import json
from datetime import datetime
from typing import Any

import httpx

from tracehound.schemas.deploys import Deploy
from tracehound.tools.source import DeploySource

_PER_PAGE = 100


class GitHubDeploySource(DeploySource):
    """Looks up what was deployed to production on GitHub during an incident window.

    Pass ``repos`` as ``{service_name: "owner/repo"}``. Tracehound expects one service per
    repository (enforced when the catalog is registered). Version and config changes come from
    the deployment payload when the pipeline sets them; otherwise version falls back to the git
    ref (branch or tag). If ``payload.service`` is set to another name, that row is skipped.
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
        """Return deploys for ``services`` that landed between ``start`` and ``end``, oldest first.

        Services not in ``repos`` are skipped. Raises if paging hits ``max_pages`` before
        reaching a deploy older than ``start``.
        """
        deploys = [
            deploy
            for service in sorted(services & self._repos.keys())
            for deploy in self._deploys_for_service(service, start, end)
        ]
        return sorted(deploys, key=lambda d: (d.deployed_at, d.id))

    def _list_raw(self, repo: str, start: datetime) -> list[dict[str, Any]]:
        """Download deployments for ``repo``, newest first, until one is older than ``start``.

        Rows older than ``start`` are only a stop signal so we know every in-window deploy was
        seen; they are not kept for ``previous_version``.
        """
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
            reached_before_start = False
            for raw in batch:
                if datetime.fromisoformat(raw["created_at"]) < start:
                    reached_before_start = True
                    break
                result.append(raw)
            if len(batch) < _PER_PAGE or reached_before_start:
                return result
        raise ValueError(f"{repo} has more than {self._max_pages} pages of deployments after start")

    def _deploys_for_service(
        self, service: str, start: datetime, end: datetime
    ) -> list[Deploy]:
        """Turn this service's GitHub deployments into in-window ``Deploy`` records.

        Keeps only deployments that belong to ``service`` and fall in ``[start, end]``.
        ``previous_version`` is left unset; change detail comes from version, commit,
        description and ``config_diff``.
        """
        deploys: list[Deploy] = []
        for raw in self._list_raw(self._repos[service], start):
            payload = raw.get("payload")
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except ValueError:
                    payload = {}
            if not isinstance(payload, dict):
                payload = {}
            named = payload.get("service")
            if named is not None and named != service:
                continue
            deployed_at = datetime.fromisoformat(raw["created_at"])
            if not (start <= deployed_at <= end):
                continue
            deploys.append(
                Deploy(
                    id=f"gh-{raw['id']}",
                    service=service,
                    version=str(payload.get("version") or raw["ref"]),
                    previous_version=None,
                    deployed_at=deployed_at,
                    author=(raw.get("creator") or {}).get("login", "unknown"),
                    commit=raw["sha"],
                    change_summary=raw.get("description") or "",
                    config_diff=payload.get("config_diff") or {},
                )
            )
        return deploys
