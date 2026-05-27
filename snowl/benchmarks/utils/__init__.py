"""Shared utility module for benchmark adapters (__init__).

Framework role:
- Provides reusable dataset/split/filter/path/task helpers consumed by multiple adapters.

Runtime/usage wiring:
- Imported by concrete benchmark adapters to reduce duplicated plumbing code.

Change guardrails:
- Keep behavior generic; benchmark-specific rules belong in adapter packages.
"""

from snowl.benchmarks.utils.filtering import matches_filters
from snowl.benchmarks.utils.io import (
    ensure_path_exists,
    read_csv_rows,
    read_json_array,
    read_json_object,
    read_jsonl_rows,
    read_yaml_mapping,
)
from snowl.benchmarks.utils.paths import default_reference_path
from snowl.benchmarks.utils.split import normalize_split
from snowl.benchmarks.utils.task_builder import build_benchmark_task
from snowl.benchmarks.utils.tool_schemas import normalize_tool_schemas
from snowl.benchmarks.assets import (
    DirectURLAsset,
    HFDatasetAsset,
    HFSnapshotFileAsset,
    benchmark_cache_root,
    stable_benchmark_id,
)

__all__ = [
    "build_benchmark_task",
    "benchmark_cache_root",
    "default_reference_path",
    "DirectURLAsset",
    "ensure_path_exists",
    "HFDatasetAsset",
    "HFSnapshotFileAsset",
    "matches_filters",
    "normalize_split",
    "normalize_tool_schemas",
    "read_csv_rows",
    "read_json_array",
    "read_json_object",
    "read_jsonl_rows",
    "read_yaml_mapping",
    "stable_benchmark_id",
]
