"""Static checks for `examples/` layout so sample projects remain runnable.

Framework role:
- Encodes the minimum example contract (`task.py`, `agent.py`, `scorer.py`) and reports structured check results.

Runtime/usage wiring:
- Used by tooling/CI flows that guard documentation and onboarding examples from drift.

Change guardrails:
- Keep checks deterministic and schema-like; avoid benchmark-specific policy in this generic validator.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ExamplesLintReport:
    ok: bool
    checks: list[dict[str, Any]]


REQUIRED_FILES = ("task.py", "agent.py", "scorer.py")


def validate_examples_layout(root: str | Path) -> ExamplesLintReport:
    root_path = Path(root).resolve()
    checks: list[dict[str, Any]] = []

    if not root_path.exists():
        checks.append(
            {
                "name": "examples_root_exists",
                "ok": False,
                "message": f"Examples root not found: {root_path}",
            }
        )
        return ExamplesLintReport(ok=False, checks=checks)

    checks.append({"name": "examples_root_exists", "ok": True, "path": str(root_path)})

    example_dirs = [
        d
        for d in sorted(root_path.iterdir())
        if d.is_dir() and not d.name.startswith(".") and d.name != "__pycache__"
    ]
    checks.append(
        {
            "name": "examples_non_empty",
            "ok": bool(example_dirs),
            "count": len(example_dirs),
            "message": "No example directories found." if not example_dirs else "",
        }
    )

    for d in example_dirs:
        missing = [name for name in REQUIRED_FILES if not (d / name).exists()]
        checks.append(
            {
                "name": "example_required_files",
                "example": d.name,
                "ok": not missing,
                "missing": missing,
                "message": (
                    ""
                    if not missing
                    else f"{d.name} is missing required files: {', '.join(missing)}"
                ),
            }
        )

    ok = all(bool(c.get("ok")) for c in checks)
    return ExamplesLintReport(ok=ok, checks=checks)

