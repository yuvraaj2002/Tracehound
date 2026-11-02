"""Record a GitHub deployment for checkout-api and apply the matching change to the running app.

`start` deploys the bad release (database pool shrunk to 5 connections, 2s timeout) and turns the
fault on; `stop` deploys the rollback and turns it off. The deployment is created at the moment
the fault starts, so the Deploy agent sees "deploy, then errors" on the real GitHub API.

    uv run python simulation/deploy.py start
    uv run python simulation/deploy.py stop

The token comes from GITHUB_TOKEN, falling back to `gh auth token`.
"""

import argparse
import os
import subprocess

import httpx

GOOD = {"version": "v1.4.1", "pool_size": 20, "timeout_s": 30}
BAD = {"version": "v1.4.2", "pool_size": 5, "timeout_s": 2}


def github_client() -> httpx.Client:
    token = (
        os.environ.get("GITHUB_TOKEN")
        or subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, check=True
        ).stdout.strip()
    )
    return httpx.Client(
        base_url="https://api.github.com",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=15,
    )


def create_deployment(gh: httpx.Client, repo: str, env: str, release: dict, before: dict) -> int:
    # Same shape as Deploy.config_diff: key -> {"old", "new"}; empty when nothing changed.
    config_diff = {
        key: {"old": str(before[field]), "new": str(release[field])}
        for key, field in (("DB_POOL_SIZE", "pool_size"), ("DB_POOL_TIMEOUT_S", "timeout_s"))
        if before[field] != release[field]
    }
    branch = gh.get(f"/repos/{repo}").raise_for_status().json()["default_branch"]
    response = gh.post(
        f"/repos/{repo}/deployments",
        json={
            "ref": branch,
            "environment": env,
            "auto_merge": False,
            "required_contexts": [],  # no CI checks in this repo
            "description": f"checkout-api {release['version']}",
            "payload": {
                "service": "checkout-api",
                "version": release["version"],
                "config_diff": config_diff,
            },
        },
    ).raise_for_status()
    deployment_id = response.json()["id"]
    gh.post(
        f"/repos/{repo}/deployments/{deployment_id}/statuses",
        json={"state": "success", "environment": env},
    ).raise_for_status()
    return deployment_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=["start", "stop"])
    parser.add_argument("--repo", default="yuvraaj2002/checkout-api-sim")
    parser.add_argument("--environment", default="production")
    parser.add_argument("--app-url", default="http://localhost:8080")
    args = parser.parse_args()

    release, before = (BAD, GOOD) if args.action == "start" else (GOOD, BAD)
    with github_client() as gh:
        existing = (
            gh.get(f"/repos/{args.repo}/deployments", params={"environment": args.environment})
            .raise_for_status()
            .json()
        )
        if not existing and args.action == "start":
            # A baseline, so the bad deploy has a previous_version to point back to.
            create_deployment(gh, args.repo, args.environment, GOOD, GOOD)
        deployment_id = create_deployment(gh, args.repo, args.environment, release, before)
    print(f"deployed {release['version']} to {args.environment} (deployment {deployment_id})")

    if args.action == "start":
        settings = {"pool_size": BAD["pool_size"], "timeout_s": BAD["timeout_s"]}
        result = httpx.post(f"{args.app_url}/admin/fault", json=settings).raise_for_status()
    else:
        result = httpx.delete(f"{args.app_url}/admin/fault").raise_for_status()
    print(f"checkout-api pool now {result.json()}")


if __name__ == "__main__":
    main()
