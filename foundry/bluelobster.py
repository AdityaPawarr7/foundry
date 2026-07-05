"""Minimal, defensive HTTP client for the Blue Lobster Instance API.

Docs: https://api.bluelobster.ai/api/v1/redoc — auth via ``X-API-Key`` header.
Response shapes vary a little across endpoints, so parsing helpers stay lenient.
"""

from __future__ import annotations

import time
from typing import Any, Callable

import httpx


class BlueLobsterError(RuntimeError):
    """Any failure talking to the Blue Lobster API."""


# Task statuses we treat as terminal when polling.
_SUCCESS_STATES = {"completed", "complete", "success", "succeeded", "done", "ready", "ok"}
_FAILURE_STATES = {"failed", "error", "errored", "cancelled", "canceled", "aborted"}


def as_list(payload: Any, *keys: str) -> list:
    """Coerce a response into a list.

    Handles endpoints that return a bare list, ``{"instances": [...]}``,
    ``{"data": [...]}``, etc.
    """
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in (*keys, "items", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        # Single object returned where a list was expected.
        return [payload]
    return []


class BlueLobsterClient:
    def __init__(
        self,
        api_key: str | None,
        base_url: str = "https://api.bluelobster.ai",
        timeout: float = 30.0,
    ) -> None:
        if not api_key:
            raise BlueLobsterError(
                "No Blue Lobster API key found. Set BLUELOBSTER_API_KEY or add "
                "[bluelobster].api_key to ~/.foundry/config.toml."
            )
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"X-API-Key": api_key, "Accept": "application/json"},
            timeout=timeout,
        )

    # -- lifecycle -------------------------------------------------------
    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "BlueLobsterClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # -- low-level -------------------------------------------------------
    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            resp = self._client.request(method, path, **kwargs)
        except httpx.RequestError as exc:
            raise BlueLobsterError(f"Network error on {method} {path}: {exc}") from exc

        if resp.status_code >= 400:
            raise BlueLobsterError(
                f"{method} {path} -> HTTP {resp.status_code}: {_error_detail(resp)}"
            )
        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            return resp.text

    def _get(self, path: str, **kw: Any) -> Any:
        return self._request("GET", path, **kw)

    def _post(self, path: str, **kw: Any) -> Any:
        return self._request("POST", path, **kw)

    def _delete(self, path: str, **kw: Any) -> Any:
        return self._request("DELETE", path, **kw)

    # -- endpoints -------------------------------------------------------
    def health(self) -> Any:
        return self._get("/api/v1/health")

    def list_instances(self) -> list[dict]:
        return as_list(self._get("/api/v1/instances"), "instances")

    def get_instance(self, instance_id: str) -> dict:
        return self._get(f"/api/v1/instances/{instance_id}")

    def instance_stats(self, instance_id: str) -> dict:
        return self._get(f"/api/v1/instances/{instance_id}/stats")

    def available(self) -> list[dict]:
        return as_list(self._get("/api/v1/instances/available"), "available", "instance_types")

    def templates(self) -> list[dict]:
        return as_list(self._get("/api/v1/instances/templates"), "templates")

    def launch(self, **body: Any) -> dict:
        return self._post("/api/v1/instances/launch-instance", json=body)

    def delete_instance(self, instance_id: str) -> Any:
        return self._delete(f"/api/v1/instances/{instance_id}")

    def reboot(self, instance_id: str) -> Any:
        return self._post(f"/api/v1/instances/{instance_id}/reboot")

    def shutdown(self, instance_id: str) -> Any:
        return self._post(f"/api/v1/instances/{instance_id}/shutdown")

    def power_on(self, instance_id: str) -> Any:
        return self._post(f"/api/v1/instances/{instance_id}/power-on")

    def get_task(self, task_id: str) -> dict:
        return self._get(f"/api/v1/tasks/{task_id}")

    # -- helpers ---------------------------------------------------------
    def poll_task(
        self,
        task_id: str,
        on_update: Callable[[dict], None] | None = None,
        interval: float = 3.0,
        timeout: float = 600.0,
    ) -> dict:
        """Poll a task until it reaches a terminal state or ``timeout`` elapses."""
        deadline = time.monotonic() + timeout
        while True:
            task = self.get_task(task_id) or {}
            if on_update:
                on_update(task)
            state = str(task.get("status") or task.get("state") or "").lower()
            if state in _SUCCESS_STATES:
                return task
            if state in _FAILURE_STATES:
                raise BlueLobsterError(
                    f"Task {task_id} failed: {task.get('message') or task.get('error') or state}"
                )
            if time.monotonic() >= deadline:
                raise BlueLobsterError(f"Timed out waiting for task {task_id} (last state: {state!r})")
            time.sleep(interval)


def _error_detail(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        return resp.text[:300] if resp.text else resp.reason_phrase
    if isinstance(body, dict):
        return str(body.get("detail") or body.get("message") or body.get("error") or body)
    return str(body)
