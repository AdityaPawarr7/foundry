"""Minimal GitHub REST client for forking a repo *as a specific token's account*.

We hit the API directly with the token rather than shelling out to ``gh``, so
the fork lands in the token's account (e.g. Concentrate's) without touching the
user's own ``gh`` login.
"""

from __future__ import annotations

import re
import time

import httpx

API_BASE = "https://api.github.com"


class GitHubError(RuntimeError):
    """Any failure talking to the GitHub API."""


_REPO_RE = re.compile(r"([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")


def parse_repo(url: str) -> tuple[str, str]:
    """Extract (owner, repo) from a URL or ``owner/repo`` string."""
    s = url.strip()
    s = re.sub(r"^https?://", "", s)
    s = re.sub(r"^git@", "", s)
    s = re.sub(r"^github\.com[:/]", "", s)
    m = _REPO_RE.search(s)
    if not m:
        raise GitHubError(f"Could not parse a GitHub owner/repo from {url!r}.")
    return m.group(1), m.group(2)


class GitHubClient:
    def __init__(self, token: str | None, timeout: float = 30.0) -> None:
        if not token:
            raise GitHubError("No GitHub token provided.")
        self._c = httpx.Client(
            base_url=API_BASE,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=timeout,
        )

    def close(self) -> None:
        self._c.close()

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _request(self, method: str, path: str, **kw) -> httpx.Response:
        try:
            r = self._c.request(method, path, **kw)
        except httpx.RequestError as exc:
            raise GitHubError(f"Network error on {method} {path}: {exc}") from exc
        if r.status_code >= 400:
            detail = ""
            try:
                detail = r.json().get("message", "")
            except ValueError:
                detail = r.text[:200]
            raise GitHubError(f"{method} {path} -> HTTP {r.status_code}: {detail}")
        return r

    def whoami(self) -> str:
        """The login of the token's account."""
        return self._request("GET", "/user").json().get("login")

    def fork(self, owner: str, repo: str) -> dict:
        """Create (or return the existing) fork in the token account. Async on GitHub."""
        return self._request("POST", f"/repos/{owner}/{repo}/forks").json()

    def wait_for_fork(
        self, fork_owner: str, repo: str, timeout: float = 90.0, interval: float = 2.0
    ) -> dict:
        """Poll until the fork repo is queryable (i.e. clonable)."""
        deadline = time.monotonic() + timeout
        while True:
            r = self._c.get(f"/repos/{fork_owner}/{repo}")
            if r.status_code == 200:
                return r.json()
            if time.monotonic() >= deadline:
                raise GitHubError(f"Fork {fork_owner}/{repo} not ready after {timeout:.0f}s.")
            time.sleep(interval)
