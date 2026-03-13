"""Low-level substrate helper (http_runner) for environment backends.

Framework role:
- Encapsulates transport/process/backend primitives used by higher env adapters.

Runtime/usage wiring:
- Consumed by terminal/gui/sandbox environment implementations.
- Key top-level symbols in this file: `HttpRunnerError`, `HttpRunner`.

Change guardrails:
- Keep API narrow and reusable; avoid introducing benchmark semantics here.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import requests


@dataclass(frozen=True)
class HttpRunnerError(RuntimeError):
    code: str
    message: str
    url: str
    method: str
    status_code: int | None = None
    retryable: bool = False

    def __str__(self) -> str:
        if self.status_code is not None:
            return f"{self.method} {self.url} failed ({self.code}, status={self.status_code}): {self.message}"
        return f"{self.method} {self.url} failed ({self.code}): {self.message}"


class HttpRunner:
    """Small requests wrapper with retries and normalized failures."""

    def __init__(self, *, default_retries: int = 0, default_retry_backoff_sec: float = 0.25) -> None:
        self._default_retries = max(0, int(default_retries))
        self._default_retry_backoff_sec = max(0.0, float(default_retry_backoff_sec))

    def get(
        self,
        url: str,
        *,
        timeout: float,
        retries: int | None = None,
        retry_backoff_sec: float | None = None,
    ):
        return self._request(
            method="GET",
            url=url,
            timeout=timeout,
            retries=retries,
            retry_backoff_sec=retry_backoff_sec,
        )

    def post(
        self,
        url: str,
        *,
        timeout: float,
        json: dict[str, Any] | None = None,
        retries: int | None = None,
        retry_backoff_sec: float | None = None,
    ):
        return self._request(
            method="POST",
            url=url,
            timeout=timeout,
            json=json,
            retries=retries,
            retry_backoff_sec=retry_backoff_sec,
        )

    def _request(
        self,
        *,
        method: str,
        url: str,
        timeout: float,
        json: dict[str, Any] | None = None,
        retries: int | None = None,
        retry_backoff_sec: float | None = None,
    ):
        retries = self._default_retries if retries is None else max(0, int(retries))
        retry_backoff_sec = (
            self._default_retry_backoff_sec
            if retry_backoff_sec is None
            else max(0.0, float(retry_backoff_sec))
        )
        attempt = 0
        while True:
            try:
                if method == "GET":
                    return requests.get(url, timeout=timeout)
                return requests.post(url, json=json, timeout=timeout)
            except requests.Timeout as exc:
                retryable = attempt < retries
                if retryable:
                    time.sleep(retry_backoff_sec * (2**attempt))
                    attempt += 1
                    continue
                raise HttpRunnerError(
                    code="timeout",
                    message=str(exc),
                    url=url,
                    method=method,
                    retryable=False,
                ) from exc
            except requests.RequestException as exc:
                status_code = None
                if getattr(exc, "response", None) is not None:
                    try:
                        status_code = int(exc.response.status_code)
                    except Exception:
                        status_code = None
                is_retryable_status = status_code == 429 or (status_code is not None and status_code >= 500)
                retryable = is_retryable_status and attempt < retries
                if retryable:
                    time.sleep(retry_backoff_sec * (2**attempt))
                    attempt += 1
                    continue
                raise HttpRunnerError(
                    code="request_error",
                    message=str(exc),
                    url=url,
                    method=method,
                    status_code=status_code,
                    retryable=False,
                ) from exc
