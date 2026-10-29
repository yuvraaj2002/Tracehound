from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from tracehound.tools.deploys import GitHubDeploySource

START = datetime(2026, 10, 15, 13, 0, tzinfo=UTC)
END = datetime(2026, 10, 15, 14, 30, tzinfo=UTC)


def _deployment(id: int, created_at: str, ref: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": id,
        "sha": f"{id:07d}",
        "ref": ref,
        "payload": {},
        "description": f"deploy {ref}",
        "creator": {"login": "deploy-bot"},
        "created_at": created_at,
        **extra,
    }


# Newest first, as GitHub returns them.
CHECKOUT = [
    _deployment(
        3,
        "2026-10-15T13:52:00Z",
        "main",
        payload={
            "version": "1.14.0",
            "config_diff": {"DB_POOL_SIZE": {"old": "20", "new": "5"}},
        },
    ),
    _deployment(2, "2026-10-15T12:00:00Z", "v1.13.4"),  # before START
    _deployment(1, "2026-10-14T12:00:00Z", "v1.13.3"),
]


def _source(
    pages: dict[str, list[list[dict[str, Any]]]],
    requests: list[httpx.Request] | None = None,
    **kwargs: Any,
) -> GitHubDeploySource:
    def handler(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        repo = request.url.path.removeprefix("/repos/").removesuffix("/deployments")
        page = int(request.url.params["page"])
        repo_pages = pages.get(repo, [])
        return httpx.Response(200, json=repo_pages[page - 1] if page <= len(repo_pages) else [])

    client = httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(handler))
    repos = kwargs.pop("repos", {"checkout-api": "acme/checkout", "payments-api": "acme/payments"})
    return GitHubDeploySource(client, repos, **kwargs)


def test_maps_deployments_and_takes_previous_version_from_older_one() -> None:
    requests: list[httpx.Request] = []
    [deploy] = _source({"acme/checkout": [CHECKOUT]}, requests).fetch({"checkout-api"}, START, END)

    params = requests[0].url.params
    assert requests[0].url.path == "/repos/acme/checkout/deployments"
    assert (params["environment"], params["per_page"]) == ("production", "100")
    assert deploy.id == "gh-3"
    assert deploy.service == "checkout-api"
    assert (deploy.previous_version, deploy.version) == ("v1.13.4", "1.14.0")
    assert deploy.deployed_at == datetime(2026, 10, 15, 13, 52, tzinfo=UTC)
    assert (deploy.author, deploy.commit) == ("deploy-bot", "0000003")
    assert deploy.config_diff == {"DB_POOL_SIZE": {"old": "20", "new": "5"}}


def test_monorepo_payload_service_and_string_payload() -> None:
    shared = [
        _deployment(5, "2026-10-15T14:00:00Z", "main", payload='{"service": "payments-api"}'),
        _deployment(4, "2026-10-15T13:30:00Z", "main", payload='{"service": "checkout-api"}'),
    ]
    source = _source(
        {"acme/mono": [shared]}, repos={"checkout-api": "acme/mono", "payments-api": "acme/mono"}
    )

    deploys = source.fetch({"checkout-api", "payments-api"}, START, END)

    assert [(d.id, d.service) for d in deploys] == [
        ("gh-4", "checkout-api"),
        ("gh-5", "payments-api"),
    ]


def test_unmapped_services_have_no_deploys_and_no_requests() -> None:
    requests: list[httpx.Request] = []
    assert _source({}, requests).fetch({"orders-db"}, START, END) == []
    assert requests == []


def test_pages_until_a_deployment_before_start() -> None:
    page = [_deployment(100 + i, "2026-10-15T14:00:00Z", "main") for i in range(100)]
    requests: list[httpx.Request] = []
    deploys = _source({"acme/checkout": [page, CHECKOUT]}, requests).fetch(
        {"checkout-api"}, START, END
    )

    assert [r.url.params["page"] for r in requests] == ["1", "2"]
    assert len(deploys) == 101


def test_too_many_pages_raises() -> None:
    page = [_deployment(100 + i, "2026-10-15T14:00:00Z", "main") for i in range(100)]
    source = _source({"acme/checkout": [page, page]}, max_pages=2)

    with pytest.raises(ValueError, match="more than 2 pages"):
        source.fetch({"checkout-api"}, START, END)
