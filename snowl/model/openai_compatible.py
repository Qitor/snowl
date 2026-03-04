"""OpenAI-compatible model client and configuration helpers."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Mapping

import httpx

from snowl.core.task_result import Timing, Usage
from snowl.errors import SnowlValidationError


@dataclass(frozen=True)
class OpenAICompatibleConfig:
    base_url: str
    api_key: str
    model: str
    timeout: float = 30.0
    max_retries: int = 2


@dataclass(frozen=True)
class ModelResponse:
    message: dict[str, Any]
    usage: Usage
    timing: Timing
    raw: dict[str, Any]


def _coerce_float(value: Any, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise SnowlValidationError(
            f"Invalid '{field_name}' value '{value}'. Expected a float."
        ) from exc


def _coerce_int(value: Any, field_name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise SnowlValidationError(
            f"Invalid '{field_name}' value '{value}'. Expected an integer."
        ) from exc


def load_openai_compatible_config(
    cli_overrides: Mapping[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
) -> OpenAICompatibleConfig:
    """Load config with precedence: CLI overrides > environment variables > defaults."""

    cli_overrides = cli_overrides or {}
    env = env or {}

    base_url = str(
        cli_overrides.get("base_url")
        or env.get("OPENAI_BASE_URL")
        or "https://api.openai.com/v1"
    ).strip()

    api_key = str(cli_overrides.get("api_key") or env.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise SnowlValidationError(
            "Missing OpenAI-compatible API key. Set OPENAI_API_KEY or pass --api-key."
        )

    model = str(cli_overrides.get("model") or env.get("OPENAI_MODEL") or "").strip()
    if not model:
        raise SnowlValidationError(
            "Missing model name. Set OPENAI_MODEL or pass --model."
        )

    timeout_raw = cli_overrides.get("timeout", env.get("OPENAI_TIMEOUT", 30.0))
    max_retries_raw = cli_overrides.get("max_retries", env.get("OPENAI_MAX_RETRIES", 2))

    timeout = _coerce_float(timeout_raw, "timeout")
    max_retries = _coerce_int(max_retries_raw, "max_retries")

    if timeout <= 0:
        raise SnowlValidationError("'timeout' must be > 0.")
    if max_retries < 0:
        raise SnowlValidationError("'max_retries' must be >= 0.")

    return OpenAICompatibleConfig(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout=timeout,
        max_retries=max_retries,
    )


class OpenAICompatibleChatClient:
    """Minimal async wrapper for OpenAI-compatible chat completion endpoints."""

    _global_model_call_limit: int | None = None
    _global_model_call_semaphore: asyncio.Semaphore | None = None

    def __init__(
        self,
        config: OpenAICompatibleConfig,
        *,
        transport: httpx.BaseTransport | httpx.AsyncBaseTransport | None = None,
        retry_backoff_seconds: float = 0.25,
    ) -> None:
        self._config = config
        self._retry_backoff_seconds = retry_backoff_seconds
        self._client = httpx.AsyncClient(
            base_url=config.base_url.rstrip("/"),
            timeout=config.timeout,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
            transport=transport,
        )

    @classmethod
    def set_global_model_call_limit(cls, limit: int | None) -> None:
        cls._global_model_call_limit = None if limit is None else max(1, int(limit))
        cls._global_model_call_semaphore = None

    async def _acquire_model_slot(self):
        if self._global_model_call_limit is None:
            return _NullAsyncContext()
        if self.__class__._global_model_call_semaphore is None:
            self.__class__._global_model_call_semaphore = asyncio.Semaphore(
                self._global_model_call_limit
            )
        return _SemaphoreAsyncContext(self.__class__._global_model_call_semaphore)

    @property
    def model(self) -> str:
        return self._config.model

    async def aclose(self) -> None:
        await self._client.aclose()

    async def generate(
        self,
        messages: list[Mapping[str, Any]],
        **generation_kwargs: Any,
    ) -> ModelResponse:
        if not isinstance(messages, list) or not messages:
            raise SnowlValidationError("'messages' must be a non-empty list.")

        payload: dict[str, Any] = {
            "model": generation_kwargs.pop("model", self._config.model),
            "messages": messages,
        }
        payload.update(generation_kwargs)

        started_at = int(time.time() * 1000)
        async with (await self._acquire_model_slot()):
            attempt = 0
            while True:
                try:
                    response = await self._client.post("/chat/completions", json=payload)
                    if response.status_code >= 400:
                        response.raise_for_status()
                    data = response.json()
                    ended_at = int(time.time() * 1000)
                    return self._normalize_response(data, started_at, ended_at)
                except (httpx.HTTPError, httpx.TimeoutException) as exc:
                    detail = self._format_exception(exc)
                    retryable = self._is_retryable_error(exc)
                    if (not retryable) or attempt >= self._config.max_retries:
                        raise SnowlValidationError(
                            f"OpenAI-compatible generate failed after {attempt + 1} attempt(s): {detail}"
                        ) from exc

                    await asyncio.sleep(self._retry_backoff_seconds * (2**attempt))
                    attempt += 1

    @staticmethod
    def _clip_text(value: str, limit: int = 360) -> str:
        text = (value or "").replace("\n", " ").strip()
        if len(text) <= limit:
            return text
        return text[: limit - 1] + "…"

    def _format_exception(self, exc: Exception) -> str:
        if isinstance(exc, httpx.HTTPStatusError):
            status = getattr(exc.response, "status_code", "unknown")
            url = str(getattr(exc.request, "url", "")) if getattr(exc, "request", None) is not None else ""
            body = ""
            try:
                body = self._clip_text(exc.response.text if exc.response is not None else "")
            except Exception:
                body = ""
            head = f"HTTP {status}"
            if url:
                head += f" {url}"
            if body:
                return f"{head} body={body}"
            return head
        if isinstance(exc, httpx.TimeoutException):
            return f"{exc.__class__.__name__}: request timed out"
        if isinstance(exc, httpx.RequestError):
            text = str(exc).strip()
            return f"{exc.__class__.__name__}: {text}" if text else exc.__class__.__name__
        text = str(exc).strip()
        if text:
            return f"{exc.__class__.__name__}: {text}"
        return exc.__class__.__name__

    def _is_retryable_error(self, exc: Exception) -> bool:
        if isinstance(exc, httpx.TimeoutException):
            return True
        if isinstance(exc, httpx.HTTPStatusError):
            try:
                status = int(getattr(exc.response, "status_code", 0) or 0)
            except Exception:
                status = 0
            return status == 429 or status >= 500
        if isinstance(exc, httpx.RequestError):
            return True
        return False

    def _normalize_response(
        self,
        data: dict[str, Any],
        started_at: int,
        ended_at: int,
    ) -> ModelResponse:
        choices = data.get("choices") or []
        if not choices:
            raise SnowlValidationError("Model response missing 'choices'.")

        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise SnowlValidationError("Model response missing first choice message.")

        usage_raw = data.get("usage") or {}
        prompt_tokens = int(usage_raw.get("prompt_tokens", 0) or 0)
        completion_tokens = int(usage_raw.get("completion_tokens", 0) or 0)
        total_tokens = int(
            usage_raw.get("total_tokens", prompt_tokens + completion_tokens) or 0
        )

        usage = Usage(
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=None,
        )
        timing = Timing(
            started_at_ms=started_at,
            ended_at_ms=ended_at,
            duration_ms=max(0, ended_at - started_at),
        )

        return ModelResponse(message=message, usage=usage, timing=timing, raw=data)


class _NullAsyncContext:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _SemaphoreAsyncContext:
    def __init__(self, sem: asyncio.Semaphore) -> None:
        self._sem = sem

    async def __aenter__(self) -> None:
        await self._sem.acquire()
        return None

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self._sem.release()
        return None
