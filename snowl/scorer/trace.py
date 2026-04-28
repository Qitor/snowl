"""Normalized trace views for scorer implementations.

Framework role:
- Provides stable extraction helpers over TaskResult and runtime trace payloads.
- Keeps benchmark scorers from depending on one agent's private event shape.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from snowl.core import TaskResult


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def assistant_text(task_result: TaskResult, trace: Mapping[str, Any] | None = None) -> str:
    _ = trace
    chunks: list[str] = []
    content = task_result.final_output.get("content")
    if content is not None:
        chunks.append(_as_text(content))
    message = task_result.final_output.get("message")
    if isinstance(message, Mapping):
        msg_content = message.get("content")
        if msg_content is not None and _as_text(msg_content) not in chunks:
            chunks.append(_as_text(msg_content))
    return "\n".join(chunk for chunk in chunks if chunk)


@dataclass(frozen=True)
class NormalizedToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    raw_arguments: Any | None = None
    call_id: str | None = None
    source: str = "trace"


def _parse_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw or "{}")
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def tool_calls(trace: Mapping[str, Any] | None = None) -> list[NormalizedToolCall]:
    if not isinstance(trace, Mapping):
        return []
    out: list[NormalizedToolCall] = []
    for action in trace.get("actions", []) or []:
        if not isinstance(action, Mapping):
            continue
        payload = action.get("payload") if isinstance(action.get("payload"), Mapping) else {}
        if str(action.get("action_type") or "") != "tool_call" and not payload:
            continue
        name = str(payload.get("tool_name") or payload.get("name") or payload.get("tool") or "").strip()
        if not name:
            continue
        raw_args = payload.get("arguments", payload.get("args", {}))
        out.append(
            NormalizedToolCall(
                name=name,
                arguments=_parse_arguments(raw_args),
                raw_arguments=raw_args,
                call_id=(str(payload.get("tool_call_id")) if payload.get("tool_call_id") is not None else None),
                source="actions",
            )
        )
    for event in trace.get("trace_events", []) or []:
        if not isinstance(event, Mapping):
            continue
        raw_calls = event.get("tool_calls")
        if not isinstance(raw_calls, Sequence) or isinstance(raw_calls, (str, bytes, bytearray)):
            continue
        for item in raw_calls:
            if not isinstance(item, Mapping):
                continue
            fn = item.get("function") if isinstance(item.get("function"), Mapping) else item
            name = str(fn.get("name") or item.get("name") or "").strip()
            if not name:
                continue
            raw_args = fn.get("arguments", item.get("arguments", {}))
            out.append(
                NormalizedToolCall(
                    name=name,
                    arguments=_parse_arguments(raw_args),
                    raw_arguments=raw_args,
                    call_id=(str(item.get("id")) if item.get("id") is not None else None),
                    source="trace_events",
                )
            )
    return out


def tool_call_text(trace: Mapping[str, Any] | None = None) -> str:
    return "\n".join(
        f"{call.name}({_as_text(call.arguments)})" for call in tool_calls(trace)
    )


def tool_result_text(trace: Mapping[str, Any] | None = None) -> str:
    if not isinstance(trace, Mapping):
        return ""
    chunks: list[str] = []
    for observation in trace.get("observations", []) or []:
        if not isinstance(observation, Mapping):
            continue
        payload = observation.get("payload") if isinstance(observation.get("payload"), Mapping) else {}
        if "result" in payload:
            chunks.append(_as_text(payload.get("result")))
    return "\n".join(chunk for chunk in chunks if chunk)


def workspace_artifacts(task_result: TaskResult, trace: Mapping[str, Any] | None = None) -> dict[str, str]:
    out: dict[str, str] = {}
    payload = task_result.payload
    for source in (
        payload.get("workspace_files"),
        payload.get("workspace_artifacts"),
        (trace or {}).get("workspace_files") if isinstance(trace, Mapping) else None,
        (trace or {}).get("workspace_artifacts") if isinstance(trace, Mapping) else None,
    ):
        if isinstance(source, Mapping):
            for path, value in source.items():
                out[str(path)] = _as_text(value)
    for artifact in task_result.artifacts:
        uri = str(artifact.uri or "")
        if uri.startswith("/") and Path(uri).is_file():
            try:
                out[artifact.name] = Path(uri).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
    return out


__all__ = [
    "NormalizedToolCall",
    "assistant_text",
    "tool_call_text",
    "tool_result_text",
    "tool_calls",
    "workspace_artifacts",
]
