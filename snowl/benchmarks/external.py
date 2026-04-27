"""External benchmark adapter loading and scaffolding helpers."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

from snowl.benchmarks.base import BenchmarkAdapter, BenchmarkInfo, validate_benchmark_adapter
from snowl.errors import SnowlValidationError


def load_external_adapter(spec: str, **kwargs: Any) -> BenchmarkAdapter:
    """Load a local benchmark adapter from ``module.py:object``.

    The exported object may be an adapter instance, a zero/kwargs factory, or a
    BenchmarkAdapter subclass. Keyword args are passed to classes/factories.
    """

    module_path, object_name = _parse_adapter_spec(spec)
    module = _load_module(module_path)
    try:
        exported = getattr(module, object_name)
    except AttributeError as exc:
        raise SnowlValidationError(
            f"External adapter object '{object_name}' not found in {module_path}."
        ) from exc

    adapter = _instantiate_adapter(exported, kwargs)
    validate_benchmark_adapter(adapter)
    return adapter


def scaffold_benchmark_adapter(name: str, *, out_dir: str | Path) -> Path:
    """Create a local third-party benchmark adapter template."""

    bench_name = _normalize_benchmark_name(name)
    class_name = "".join(part.capitalize() for part in re.split(r"[^a-zA-Z0-9]+", bench_name) if part) + "Adapter"
    target = Path(out_dir).resolve()
    target.mkdir(parents=True, exist_ok=True)

    _write_if_missing(
        target / "data.jsonl",
        "\n".join(
            [
                json.dumps(
                    {
                        "id": "sample-1",
                        "split": "test",
                        "input": "Say hello in one short sentence.",
                        "target": "hello",
                        "category": "smoke",
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "id": "sample-2",
                        "split": "dev",
                        "input": "Say goodbye in one short sentence.",
                        "target": "goodbye",
                        "category": "smoke",
                    },
                    ensure_ascii=False,
                ),
            ]
        )
        + "\n",
    )
    _write_if_missing(
        target / "adapter.py",
        f'''from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from snowl.benchmarks.base import BenchmarkInfo
from snowl.benchmarks.base_adapter import BaseBenchmarkAdapter
from snowl.benchmarks.utils import read_jsonl_rows


@dataclass(frozen=True)
class {class_name}(BaseBenchmarkAdapter[dict[str, Any]]):
    dataset_path: str = "data.jsonl"
    name: str = "{bench_name}"
    description: str = "{bench_name} third-party benchmark adapter."
    default_split: str = "test"

    def benchmark_info(self) -> BenchmarkInfo:
        return BenchmarkInfo(
            name=self.name,
            description=self.description,
            domain="custom",
            benchmark_type="safety",
            family=self.name,
            primary_metric="accuracy",
            higher_is_better=True,
            sample_preview_mode="qa",
            dashboard_tags=["third_party"],
        )

    def _iter_rows(self) -> list[dict[str, Any]]:
        return read_jsonl_rows(self.dataset_path, not_found_message=f"{{self.name}} dataset not found")

    def _row_split(self, row: dict[str, Any], *, row_index: int) -> str:
        _ = row_index
        return str(row.get("split") or self.default_split)

    def _row_to_sample(
        self,
        row: dict[str, Any],
        *,
        row_index: int,
        row_split: str,
        selected_count: int,
    ) -> dict[str, Any] | None:
        prompt = str(row.get("input") or "").strip()
        if not prompt:
            return None
        return {{
            "id": str(row.get("id") or f"{{row_split}}-{{selected_count + 1}}"),
            "input": prompt,
            "target": row.get("target"),
            "metadata": {{
                "target": row.get("target"),
                "category": row.get("category"),
                "row_index": row_index,
                "split": row_split,
            }},
        }}


def adapter(**kwargs: Any) -> {class_name}:
    return {class_name}(**kwargs)
''',
    )
    _write_if_missing(
        target / "scorer.py",
        '''from __future__ import annotations

from snowl.core import Score


class AccuracyScorer:
    scorer_id = "accuracy"

    def score(self, task_result, trace, context):
        target = str(context.sample_metadata.get("target") or "").strip().lower()
        output = task_result.final_output or {}
        message = output.get("message") if isinstance(output, dict) else {}
        content = str((message or {}).get("content") or output.get("content") or "").strip().lower()
        if not target:
            return {"accuracy": Score(value=1.0)}
        return {"accuracy": Score(value=1.0 if target in content else 0.0)}


scorer = AccuracyScorer()
''',
    )
    _write_if_missing(
        target / "README.md",
        f"""# {bench_name} Snowl Adapter

Run conformance:

```bash
snowl bench check {bench_name} --adapter ./adapter.py:adapter --adapter-arg dataset_path=./data.jsonl
```

Run with a Snowl project:

```bash
snowl bench run {bench_name} --adapter ./adapter.py:adapter --project ../project.yml --split test --limit 1 --adapter-arg dataset_path=./data.jsonl
```

Keep sample ids stable. They become part of retry, artifact, and dashboard identity.
""",
    )
    _write_if_missing(
        target / "project-snippet.yml",
        f"""# Add this benchmark via CLI:
# snowl bench run {bench_name} --adapter ./adapter.py:adapter --adapter-arg dataset_path=./data.jsonl --project ./project.yml
""",
    )
    return target


def _parse_adapter_spec(spec: str) -> tuple[Path, str]:
    raw = str(spec or "").strip()
    if ":" not in raw:
        raise SnowlValidationError("External adapter must use module.py:object format.")
    module_raw, object_name = raw.rsplit(":", 1)
    module_path = Path(module_raw).expanduser().resolve()
    object_name = object_name.strip()
    if not module_path.exists():
        raise SnowlValidationError(f"External adapter module not found: {module_path}")
    if not object_name:
        raise SnowlValidationError("External adapter object name must be non-empty.")
    return module_path, object_name


def _load_module(module_path: Path):
    module_name = f"_snowl_external_adapter_{abs(hash(str(module_path)))}"
    spec = importlib.util.spec_from_file_location(module_name, str(module_path))
    if spec is None or spec.loader is None:
        raise SnowlValidationError(f"Failed to load external adapter module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise SnowlValidationError(f"External adapter module failed to import: {module_path}: {exc}") from exc
    return module


def _instantiate_adapter(exported: Any, kwargs: dict[str, Any]) -> BenchmarkAdapter:
    if isinstance(exported, type):
        adapter = exported(**kwargs)
    elif callable(exported):
        adapter = exported(**kwargs)
    else:
        if kwargs:
            raise SnowlValidationError("External adapter instance cannot accept --adapter-arg values.")
        adapter = exported
    validate_benchmark_adapter(adapter)
    return adapter


def _normalize_benchmark_name(name: str) -> str:
    out = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(name or "").strip()).strip("-").lower()
    if not out:
        raise SnowlValidationError("Benchmark scaffold name must be non-empty.")
    return out


def _write_if_missing(path: Path, content: str) -> None:
    if path.exists():
        raise SnowlValidationError(f"Refusing to overwrite existing scaffold file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
