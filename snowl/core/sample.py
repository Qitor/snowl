"""Structured Sample model for typed evaluation data.

Framework role:
- Defines ``Sample`` as a typed replacement for raw ``dict`` samples.
- Provides ``to_dict()`` / ``from_dict()`` for backward compatibility.
- ``Task.iter_samples()`` accepts both ``Sample`` and ``dict`` inputs.

Runtime/usage wiring:
- Used by ``BaseBenchmarkAdapter._row_to_sample()`` to return typed samples.
- ``AgentContext`` and ``ScoreContext`` carry the full ``Sample`` for scorer access.

Change guardrails:
- Must not import third-party packages (core/ boundary rule).
- ``Sample`` is a frozen dataclass; new optional fields must have defaults.
- Dict-based samples remain fully supported — no breaking change.

Reference:
- ``references/inspect_ai/src/inspect_ai/dataset/_dataset.py`` (Inspect AI Sample)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Sample:
    """Structured evaluation sample.

    Replaces raw ``{"id": ..., "input": ..., "metadata": ...}`` dicts with
    a typed, validated model. Fully backward-compatible: ``from_dict()``
    converts legacy dicts, ``to_dict()`` exports legacy format.

    Reference: ``references/inspect_ai/src/inspect_ai/dataset/_dataset.py`` (Sample)
    """

    id: str
    input: str | list[dict[str, Any]]
    target: str | list[str] | None = None
    choices: list[str] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    files: dict[str, str] | None = None
    sandbox_override: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to legacy dict format for backward compatibility."""
        d: dict[str, Any] = {"id": self.id, "input": self.input}
        if self.target is not None:
            d["target"] = self.target
        if self.choices is not None:
            d["choices"] = self.choices
        if self.metadata:
            d["metadata"] = dict(self.metadata)
        if self.files is not None:
            d["files"] = dict(self.files)
        if self.sandbox_override is not None:
            d["sandbox_override"] = dict(self.sandbox_override)
        return d

    def __getitem__(self, key: str) -> Any:
        """Dict-style access for backward compatibility."""
        return self.to_dict()[key]

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-compatible get() for backward compatibility."""
        return self.to_dict().get(key, default)

    def keys(self) -> list[str]:
        """Dict-compatible keys() for ``dict(sample)`` support."""
        return list(self.to_dict().keys())

    def __iter__(self):
        """Dict-compatible iteration for ``dict(sample)`` support."""
        return iter(self.to_dict())

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Sample":
        """Create a Sample from a legacy dict.

        Handles both new-format dicts (with target/choices) and
        old-format dicts (with just id/input/metadata).
        """
        return cls(
            id=str(d.get("id", "")),
            input=d.get("input", ""),
            target=d.get("target"),
            choices=d.get("choices"),
            metadata=dict(d.get("metadata") or {}),
            files=dict(d.get("files")) if isinstance(d.get("files"), dict) else None,
            sandbox_override=dict(d.get("sandbox_override")) if isinstance(d.get("sandbox_override"), dict) else None,
        )
