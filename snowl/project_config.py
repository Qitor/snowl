"""Canonical `project.yml` loader/validator for provider, model matrix, code modules, runtime budgets, and recovery policy.

Framework role:
- Defines the external configuration contract consumed by eval and benchmark runs.
- Converts raw YAML into typed config objects used across runtime, model, and discovery layers.

Runtime/usage wiring:
- Used by eval bootstrap, benchmark orchestration, and model-variant expansion helpers.
- Configuration defaults here directly influence runtime controls and recovery semantics.
- Key top-level symbols in this file: `ProjectProviderConfig`, `ProjectModelEntry`, `ProjectJudgeConfig`, `ProjectCodeConfig`, `ProjectEvalConfig`, `ProjectRuntimeConfig`.

Change guardrails:
- Contract changes require synchronized updates to docs, examples, and tests.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from snowl.errors import SnowlValidationError
from snowl.model.openai_compatible import OpenAICompatibleConfig


@dataclass(frozen=True)
class ProjectProviderConfig:
    id: str
    kind: str
    base_url: str
    api_key: str
    timeout: float
    max_retries: int


@dataclass(frozen=True)
class ProjectModelEntry:
    id: str
    model: str
    config: OpenAICompatibleConfig
    metadata: dict[str, str] | None = None
    provider_override: dict[str, str] | None = None


@dataclass(frozen=True)
class ProjectJudgeConfig:
    model: str
    config: OpenAICompatibleConfig


@dataclass(frozen=True)
class ProjectCodeConfig:
    base_dir: Path
    task_module: Path
    agent_module: Path
    scorer_module: Path
    tool_module: Path | None = None


@dataclass(frozen=True)
class ProjectEvalConfig:
    benchmark: str
    code: ProjectCodeConfig
    split: str | None = None
    limit: int | None = None
    agent_type: str | None = None  # "native" | "emulated" | "stateful"
    agent_config: dict[str, Any] | None = None


@dataclass(frozen=True)
class ProjectRuntimeConfig:
    max_running_trials: int | None = None
    max_container_slots: int | str | None = "auto"
    max_builds: int | None = None
    max_scoring_tasks: int | None = None
    provider_budgets: dict[str, int] = field(default_factory=dict)
    recovery: "ProjectRecoveryConfig" = field(default_factory=lambda: ProjectRecoveryConfig())


@dataclass(frozen=True)
class ProjectRecoveryConfig:
    auto_retry_non_success: bool = True
    max_auto_retries_per_trial: int = 1
    retry_timing: str = "deferred"
    backoff_ms: int = 2000


@dataclass(frozen=True)
class ProjectConfig:
    path: Path
    root_dir: Path
    name: str
    provider: ProjectProviderConfig
    agent_matrix: list[ProjectModelEntry]
    judge: ProjectJudgeConfig | None
    eval: ProjectEvalConfig
    runtime: ProjectRuntimeConfig
    benchmarks: dict[str, Any]
    raw: dict[str, Any]

    @property
    def models(self) -> list[ProjectModelEntry]:
        return self.agent_matrix

    def benchmark_settings(self, benchmark_name: str | None = None) -> dict[str, Any]:
        target = str(benchmark_name or self.eval.benchmark or "").strip()
        if not target:
            return {}
        raw = self.benchmarks.get(target, {})
        return dict(raw) if isinstance(raw, dict) else {}


def find_project_file(path: str | Path) -> Path | None:
    resolved = Path(path).resolve()
    if resolved.is_file():
        if resolved.name in {"project.yml", "project.yaml"}:
            return resolved
        return None
    for name in ("project.yml", "project.yaml"):
        candidate = resolved / name
        if candidate.exists():
            return candidate
    return None


def _substitute_env_vars(value: Any) -> Any:
    """Recursively replace ${VAR} and ${env:VAR} patterns with os.environ values."""
    if isinstance(value, str):
        import re
        pattern = re.compile(r"\$\{(?:env:)?(\w+)\}")

        def _replace(match: re.Match) -> str:
            var_name = match.group(1)
            env_value = os.environ.get(var_name)
            if env_value is None:
                raise SnowlValidationError(
                    f"Environment variable '{var_name}' referenced in project.yml but not set"
                )
            return env_value

        return pattern.sub(_replace, value)
    if isinstance(value, dict):
        return {k: _substitute_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env_vars(item) for item in value]
    return value


def load_project_config(path: str | Path) -> ProjectConfig:
    config_path = find_project_file(path)
    if config_path is None:
        raise SnowlValidationError(f"Missing project.yml for {Path(path).resolve()}")

    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        raise SnowlValidationError(f"Failed to parse project config: {config_path}: {exc}") from exc
    data = _require_mapping(raw, label="project config", path=config_path)
    data = _substitute_env_vars(data)
    project_data = _require_mapping(data.get("project"), label="project", path=config_path)
    project_data = _require_mapping(data.get("project"), label="project", path=config_path)
    project_root = _resolve_dir(
        project_data.get("root_dir"),
        base=config_path.parent,
        default=config_path.parent,
        label="project.root_dir",
        path=config_path,
    )
    project_name = _require_non_empty_str(
        project_data.get("name") or project_root.name,
        label="project.name",
        path=config_path,
    )

    provider_data = _require_mapping(data.get("provider"), label="provider", path=config_path)
    provider_kind = _require_non_empty_str(provider_data.get("kind"), label="provider.kind", path=config_path)
    if provider_kind != "openai_compatible":
        raise SnowlValidationError(
            f"Unsupported provider.kind '{provider_kind}' in {config_path}; only openai_compatible is supported."
        )
    provider = ProjectProviderConfig(
        id=_require_non_empty_str(provider_data.get("id") or "default", label="provider.id", path=config_path),
        kind=provider_kind,
        base_url=_require_non_empty_str(provider_data.get("base_url"), label="provider.base_url", path=config_path),
        api_key=_require_non_empty_str(provider_data.get("api_key"), label="provider.api_key", path=config_path),
        timeout=_coerce_timeout(provider_data.get("timeout"), path=config_path),
        max_retries=_coerce_max_retries(provider_data.get("max_retries"), path=config_path),
    )

    matrix_data = _require_mapping(data.get("agent_matrix"), label="agent_matrix", path=config_path)
    models_raw = matrix_data.get("models")
    if not isinstance(models_raw, list) or not models_raw:
        raise SnowlValidationError(f"agent_matrix.models must be a non-empty list in {config_path}")
    seen_ids: set[str] = set()
    seen_models: set[str] = set()
    models: list[ProjectModelEntry] = []
    for index, item in enumerate(models_raw, start=1):
        row = _require_mapping(item, label=f"agent_matrix.models[{index}]", path=config_path)
        model_id = _require_non_empty_str(row.get("id"), label=f"agent_matrix.models[{index}].id", path=config_path)
        model_name = _require_non_empty_str(
            row.get("model"),
            label=f"agent_matrix.models[{index}].model",
            path=config_path,
        )
        if model_id in seen_ids:
            raise SnowlValidationError(f"Duplicate agent_matrix model id '{model_id}' in {config_path}")
        if model_name in seen_models:
            raise SnowlValidationError(f"Duplicate agent_matrix model '{model_name}' in {config_path}")
        seen_ids.add(model_id)
        seen_models.add(model_name)

        # Parse optional model metadata for dashboard filtering
        model_metadata = _parse_model_metadata(row.get("metadata"), path=config_path)

        # Allow per-model provider override (base_url, api_key)
        provider_override_raw = row.get("provider")
        provider_override: dict[str, str] | None = None
        if provider_override_raw is not None and isinstance(provider_override_raw, dict):
            provider_override = {
                k: str(v).strip()
                for k, v in provider_override_raw.items()
                if k in ("base_url", "api_key") and str(v).strip()
            }

        # Use per-model provider override if provided, otherwise use global provider
        model_base_url = provider.base_url
        model_api_key = provider.api_key
        has_provider_override = False
        if provider_override:
            model_base_url = provider_override.get("base_url", provider.base_url)
            model_api_key = provider_override.get("api_key", provider.api_key)
            has_provider_override = model_base_url != provider.base_url

        # Generate per-endpoint provider_id when model uses a different endpoint
        # so that the scheduler can budget each endpoint independently.
        model_provider_id = provider.id
        if has_provider_override:
            model_provider_id = _derive_endpoint_provider_id(provider.id, model_base_url)

        models.append(
            ProjectModelEntry(
                id=model_id,
                model=model_name,
                config=OpenAICompatibleConfig(
                    provider_id=model_provider_id,
                    base_url=model_base_url,
                    api_key=model_api_key,
                    model=model_name,
                    timeout=provider.timeout,
                    max_retries=provider.max_retries,
                ),
                metadata=model_metadata,
                provider_override=provider_override if provider_override else None,
            )
        )

    judge_data = data.get("judge")
    judge: ProjectJudgeConfig | None = None
    if judge_data is not None:
        judge_row = _require_mapping(judge_data, label="judge", path=config_path)
        judge_model = _require_non_empty_str(judge_row.get("model"), label="judge.model", path=config_path)
        judge = ProjectJudgeConfig(
            model=judge_model,
            config=OpenAICompatibleConfig(
                provider_id=provider.id,
                base_url=provider.base_url,
                api_key=provider.api_key,
                model=judge_model,
                timeout=provider.timeout,
                max_retries=provider.max_retries,
            ),
        )

    eval_data = _require_mapping(data.get("eval"), label="eval", path=config_path)
    code_data = _require_mapping(eval_data.get("code"), label="eval.code", path=config_path)
    code_base_dir = _resolve_dir(
        code_data.get("base_dir"),
        base=project_root,
        default=project_root,
        label="eval.code.base_dir",
        path=config_path,
    )
    code = ProjectCodeConfig(
        base_dir=code_base_dir,
        task_module=_resolve_file(code_data.get("task_module"), base=code_base_dir, label="eval.code.task_module", path=config_path),
        agent_module=_resolve_file(code_data.get("agent_module"), base=code_base_dir, label="eval.code.agent_module", path=config_path),
        scorer_module=_resolve_file(code_data.get("scorer_module"), base=code_base_dir, label="eval.code.scorer_module", path=config_path),
        tool_module=_resolve_optional_file(code_data.get("tool_module"), base=code_base_dir),
    )
    eval_cfg = ProjectEvalConfig(
        benchmark=_require_non_empty_str(eval_data.get("benchmark"), label="eval.benchmark", path=config_path),
        code=code,
        split=_coerce_optional_str(eval_data.get("split")),
        limit=_coerce_optional_int(eval_data.get("limit"), label="eval.limit", path=config_path),
        agent_type=_coerce_optional_str(eval_data.get("agent_type")),
        agent_config=dict(eval_data["agent_config"]) if isinstance(eval_data.get("agent_config"), dict) else None,
    )

    runtime_data = _require_mapping(data.get("runtime") or {}, label="runtime", path=config_path)
    provider_budgets_raw = runtime_data.get("provider_budgets") or {}
    if not isinstance(provider_budgets_raw, dict):
        raise SnowlValidationError(f"runtime.provider_budgets must be a mapping in {config_path}")
    provider_budgets: dict[str, int] = {}
    for key, value in provider_budgets_raw.items():
        provider_key = _require_non_empty_str(key, label="runtime.provider_budgets key", path=config_path)
        provider_budgets[provider_key] = _coerce_positive_int(value, label=f"runtime.provider_budgets.{provider_key}", path=config_path)
    recovery_data = _require_mapping(runtime_data.get("recovery") or {}, label="runtime.recovery", path=config_path)
    retry_timing = str(recovery_data.get("retry_timing") or "deferred").strip().lower() or "deferred"
    if retry_timing != "deferred":
        raise SnowlValidationError(f"runtime.recovery.retry_timing must be 'deferred' in {config_path}")
    runtime = ProjectRuntimeConfig(
        max_running_trials=_coerce_optional_int(runtime_data.get("max_running_trials"), label="runtime.max_running_trials", path=config_path),
        max_container_slots=_coerce_auto_int(runtime_data.get("max_container_slots"), label="runtime.max_container_slots", path=config_path),
        max_builds=_coerce_optional_int(runtime_data.get("max_builds"), label="runtime.max_builds", path=config_path),
        max_scoring_tasks=_coerce_optional_int(runtime_data.get("max_scoring_tasks"), label="runtime.max_scoring_tasks", path=config_path),
        provider_budgets=provider_budgets,
        recovery=ProjectRecoveryConfig(
            auto_retry_non_success=_coerce_bool(recovery_data.get("auto_retry_non_success"), default=True),
            max_auto_retries_per_trial=_coerce_non_negative_int(
                recovery_data.get("max_auto_retries_per_trial"),
                label="runtime.recovery.max_auto_retries_per_trial",
                path=config_path,
                default=1,
            ),
            retry_timing=retry_timing,
            backoff_ms=_coerce_non_negative_int(
                recovery_data.get("backoff_ms"),
                label="runtime.recovery.backoff_ms",
                path=config_path,
                default=2000,
            ),
        ),
    )

    benchmarks_raw = data.get("benchmarks") or {}
    if not isinstance(benchmarks_raw, dict):
        raise SnowlValidationError(f"benchmarks must be a mapping in {config_path}")

    return ProjectConfig(
        path=config_path,
        root_dir=project_root,
        name=project_name,
        provider=provider,
        agent_matrix=models,
        judge=judge,
        eval=eval_cfg,
        runtime=runtime,
        benchmarks=dict(benchmarks_raw),
        raw=data,
    )


def _require_mapping(value: Any, *, label: str, path: Path) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SnowlValidationError(f"{label} must be a mapping in {path}")
    return dict(value)


def _derive_endpoint_provider_id(parent_id: str, base_url: str) -> str:
    """Derive a unique provider_id from the base_url for per-endpoint budgeting.

    Format: ``{parent_id}__{slug}`` where slug is derived from the hostname.
    Example: ``inf__o8kjqm58o8ogcm5ek8aggddkb5ggk8dp``
    """
    import re

    from urllib.parse import urlparse

    parsed = urlparse(base_url)
    host = (parsed.hostname or "").lower()
    # Take the first subdomain segment as a slug (e.g. "o8kjqm58o8ogcm5ek8aggddkb5ggk8dp")
    parts = host.split(".")
    slug = parts[0] if parts else host
    # Clean to alphanumeric + dash only
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    if not slug:
        slug = "custom"
    return f"{parent_id}__{slug}"


def _require_non_empty_str(value: Any, *, label: str, path: Path) -> str:
    text = str(value or "").strip()
    if not text:
        raise SnowlValidationError(f"{label} must be a non-empty string in {path}")
    return text


def _coerce_timeout(value: Any, *, path: Path) -> float:
    try:
        timeout = float(value if value is not None else 30.0)
    except Exception as exc:
        raise SnowlValidationError(f"provider.timeout must be numeric in {path}") from exc
    if timeout <= 0:
        raise SnowlValidationError(f"provider.timeout must be > 0 in {path}")
    return timeout


def _coerce_max_retries(value: Any, *, path: Path) -> int:
    try:
        retries = int(value if value is not None else 2)
    except Exception as exc:
        raise SnowlValidationError(f"provider.max_retries must be an integer in {path}") from exc
    if retries < 0:
        raise SnowlValidationError(f"provider.max_retries must be >= 0 in {path}")
    return retries


def _coerce_optional_int(value: Any, *, label: str, path: Path) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    return _coerce_positive_int(value, label=label, path=path)


_VALID_SOURCE_TYPES = {"open_source", "closed_source"}
_VALID_REASONING_LEVELS = {"none", "low", "medium", "high", "unknown"}


def _parse_model_metadata(raw: Any, *, path: Path) -> dict[str, str] | None:
    """Parse and validate optional model metadata dict from YAML."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise SnowlValidationError(f"model metadata must be a mapping in {path}")

    result: dict[str, str] = {}
    for key, value in raw.items():
        str_key = str(key).strip()
        if not str_key:
            continue
        str_value = str(value).strip()
        result[str_key] = str_value

    # Validate enum fields if present
    source_type = result.get("source_type")
    if source_type is not None and source_type not in _VALID_SOURCE_TYPES:
        raise SnowlValidationError(
            f"model metadata source_type must be one of {_VALID_SOURCE_TYPES}, got '{source_type}' in {path}"
        )

    reasoning = result.get("reasoning")
    if reasoning is not None and reasoning not in _VALID_REASONING_LEVELS:
        raise SnowlValidationError(
            f"model metadata reasoning must be one of {_VALID_REASONING_LEVELS}, got '{reasoning}' in {path}"
        )

    # Normalize string fields
    for key in ("company", "country", "model_family"):
        val = result.get(key)
        if val is not None:
            result[key] = val.strip()

    return result if result else None


def _coerce_non_negative_int(value: Any, *, label: str, path: Path, default: int | None = None) -> int:
    if value is None:
        if default is None:
            raise SnowlValidationError(f"{label} must be >= 0 in {path}")
        return int(default)
    try:
        parsed = int(value)
    except Exception as exc:
        raise SnowlValidationError(f"{label} must be an integer in {path}") from exc
    if parsed < 0:
        raise SnowlValidationError(f"{label} must be >= 0 in {path}")
    return parsed


def _coerce_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _coerce_positive_int(value: Any, *, label: str, path: Path) -> int:
    try:
        parsed = int(value)
    except Exception as exc:
        raise SnowlValidationError(f"{label} must be an integer in {path}") from exc
    if parsed <= 0:
        raise SnowlValidationError(f"{label} must be > 0 in {path}")
    return parsed


def _coerce_auto_int(value: Any, *, label: str, path: Path) -> int | str | None:
    if value is None or str(value).strip() == "":
        return "auto"
    if isinstance(value, str) and value.strip().lower() == "auto":
        return "auto"
    return _coerce_non_negative_int(value, label=label, path=path)


def _coerce_optional_str(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _resolve_dir(value: Any, *, base: Path, default: Path, label: str, path: Path) -> Path:
    if value is None or str(value).strip() == "":
        candidate = default.resolve()
    else:
        candidate = _resolve_path(base=base, value=value).resolve()
    if not candidate.exists():
        raise SnowlValidationError(f"{label} does not exist in {path}: {candidate}")
    if not candidate.is_dir():
        raise SnowlValidationError(f"{label} must be a directory in {path}: {candidate}")
    return candidate


def _resolve_file(value: Any, *, base: Path, label: str, path: Path) -> Path:
    candidate = _resolve_path(base=base, value=value).resolve()
    if not candidate.exists():
        raise SnowlValidationError(f"{label} does not exist in {path}: {candidate}")
    if not candidate.is_file():
        raise SnowlValidationError(f"{label} must be a file in {path}: {candidate}")
    return candidate


def _resolve_optional_file(value: Any, *, base: Path) -> Path | None:
    if value is None or str(value).strip() == "":
        return None
    candidate = _resolve_path(base=base, value=value).resolve()
    return candidate if candidate.exists() and candidate.is_file() else None


def _resolve_path(*, base: Path, value: Any) -> Path:
    candidate = Path(str(value))
    if candidate.is_absolute():
        return candidate
    return (base / candidate).resolve()
